from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.core.openai.requests import ResponsesRequest
from app.core.utils.request_id import reset_request_id, set_request_id
from app.db.models import Account
from app.modules.proxy import service as proxy_service
from app.modules.proxy._service.streaming import helpers as streaming_helpers
from app.modules.proxy.load_balancer import AccountSelection
from tests.unit.test_proxy_utils import (
    _make_account,
    _make_proxy_settings,
    _repo_factory,
    _RequestLogsRecorder,
    _SettingsCache,
)

_MESSAGE = "response protection is unavailable"
_SECRET = "Bearer super-secret-token"
_IMAGE = "data:image/png;base64,iVBORw0KGgoSECRETIMAGE"


def _sse(payload: dict[str, Any]) -> str:
    return "data: " + json.dumps(payload) + "\n\n"


def _protection_error(
    *,
    message: str = _MESSAGE,
    param: str | None = "input_image",
) -> str:
    error: dict[str, Any] = {
        "code": "internal_error",
        "message": message,
        "type": "server_error",
    }
    if param is not None:
        error["param"] = param
    return _sse({"type": "error", "error": error})


def _completed(response_id: str) -> str:
    return _sse(
        {
            "type": "response.completed",
            "response": {"id": response_id, "usage": {"input_tokens": 1, "output_tokens": 2}},
        }
    )


def _created(response_id: str) -> str:
    return _sse({"type": "response.created", "response": {"id": response_id}})


def _text_delta(text: str = "hi") -> str:
    return _sse(
        {
            "type": "response.output_text.delta",
            "delta": text,
            "output_index": 0,
            "content_index": 0,
        }
    )


def _events(chunks: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        if "data: " not in chunk:
            continue
        events.append(json.loads(chunk.split("data: ", 1)[1].strip()))
    return events


def _upstream_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage() for record in caplog.records if record.getMessage().startswith("upstream stream error ")
    ]


def test_response_protection_message_match_is_exact() -> None:
    assert streaming_helpers._is_response_protection_unavailable("internal_error", _MESSAGE) is True
    assert (
        streaming_helpers._is_response_protection_unavailable(
            "internal_error",
            "  Response\nProtection   is\tunavailable  ",
        )
        is True
    )
    assert (
        streaming_helpers._is_response_protection_unavailable(
            "internal_error",
            "response protection is unavailable, try again",
        )
        is False
    )
    assert streaming_helpers._is_response_protection_unavailable("server_error", _MESSAGE) is False
    detail = streaming_helpers._upstream_stream_error_metadata(
        code="internal_error",
        message="response protection is unavailable",
        error_type="server_error",
        param="input_image",
    )
    assert detail.failure_phase == "upstream"
    assert detail.upstream_error_code == "internal_error"
    assert detail.failure_detail == "response protection is unavailable type=server_error param=input_image"
    long_detail = streaming_helpers._upstream_stream_error_metadata(
        code="internal_error",
        message="x" * 500,
        error_type="server_error",
        param=None,
    )
    assert long_detail.failure_detail is not None
    assert len(long_detail.failure_detail) < 500
    assert "\n" not in long_detail.failure_detail


class _StreamHarness:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, account_ids: list[str]) -> None:
        self.settings = _make_proxy_settings()
        self.request_logs = _RequestLogsRecorder()
        self.service = proxy_service.ProxyService(_repo_factory(self.request_logs))
        self.accounts = [_make_account(account_id) for account_id in account_ids]
        self.seen_excluded: list[set[str]] = []
        self.stream_accounts: list[str | None] = []
        monkeypatch.setattr(proxy_service, "get_settings_cache", lambda: _SettingsCache(self.settings))
        monkeypatch.setattr(proxy_service, "get_settings", lambda: self.settings)

        async def select_account(**kwargs: object) -> AccountSelection:
            excluded = set(cast(set[str] | None, kwargs.get("exclude_account_ids")) or set())
            self.seen_excluded.append(excluded)
            for account in self.accounts:
                if account.id not in excluded:
                    return AccountSelection(account=account, error_message=None)
            return AccountSelection(
                account=None, error_message="No active accounts available", error_code="no_accounts"
            )

        async def ensure_fresh(account: Account, **_kwargs: object) -> Account:
            return account

        monkeypatch.setattr(self.service._load_balancer, "select_account", select_account)
        monkeypatch.setattr(self.service._load_balancer, "record_error", AsyncMock())
        monkeypatch.setattr(self.service._load_balancer, "record_errors", AsyncMock())
        monkeypatch.setattr(self.service._load_balancer, "record_success", AsyncMock())
        monkeypatch.setattr(self.service, "_ensure_fresh_with_budget", ensure_fresh)

        async def _instant_sleep(*_args: object, **_kwargs: object) -> None:
            return None

        monkeypatch.setattr("app.modules.proxy._service.streaming.retry.asyncio.sleep", _instant_sleep)

    def install_stream(self, monkeypatch: pytest.MonkeyPatch, script: dict[str | None, list[list[str]]]) -> None:
        cursors = {account_id: 0 for account_id in script}

        async def fake_stream(
            _payload: ResponsesRequest,
            _headers: Mapping[str, str],
            _access_token: str,
            account_id: str | None,
            base_url: str | None = None,
            raise_for_status: bool = False,
        ) -> AsyncIterator[str]:
            del base_url, raise_for_status
            self.stream_accounts.append(account_id)
            attempts = script[account_id]
            index = cursors[account_id]
            cursors[account_id] = index + 1
            for line in attempts[index]:
                yield line

        monkeypatch.setattr(proxy_service, "core_stream_responses", fake_stream)

    async def stream(self, *, request_id: str, input_value: object | None = None) -> list[str]:
        payload_input: object = input_value if input_value is not None else []
        payload = ResponsesRequest.model_validate(
            {"model": "gpt-5.6-sol", "instructions": "hi", "input": payload_input, "stream": True}
        )
        token = set_request_id(request_id)
        try:
            return [
                chunk
                async for chunk in self.service.stream_responses(
                    payload,
                    {"session_id": "sid-protection", "authorization": _SECRET},
                )
            ]
        finally:
            reset_request_id(token)


def _image_input() -> list[dict[str, object]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "describe"},
                {"type": "input_image", "image_url": _IMAGE},
            ],
        }
    ]


@pytest.mark.asyncio
async def test_response_protection_retries_same_account_before_output(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING", logger="app.modules.proxy.service")
    harness = _StreamHarness(monkeypatch, ["acc_protection_same"])
    account_id = harness.accounts[0].chatgpt_account_id
    harness.install_stream(
        monkeypatch,
        {
            account_id: [
                [_protection_error(message="  Response Protection is Unavailable  ")],
                [_completed("resp_protection_ok")],
            ]
        },
    )

    chunks = await harness.stream(request_id="req_protection_same", input_value=_image_input())

    events = _events(chunks)
    assert [event["type"] for event in events] == ["response.completed"]
    assert events[0]["response"]["id"] == "resp_protection_ok"
    assert harness.stream_accounts == [account_id, account_id]
    assert harness.seen_excluded == [set()]
    assert await harness.service.drain_persistence_tasks(timeout_seconds=1)
    assert [call["status"] for call in harness.request_logs.calls] == ["error", "success"]
    failed = harness.request_logs.calls[0]
    assert failed["request_id"] == "req_protection_same"
    assert failed["archive_request_id"] == "req_protection_same"
    assert failed["error_code"] == "internal_error"
    assert failed["upstream_error_code"] == "internal_error"
    assert failed["failure_phase"] == "upstream"
    assert failed["upstream_status_code"] is None
    detail = str(failed["failure_detail"])
    assert "response protection is unavailable" in detail.casefold()
    assert "type=server_error" in detail
    assert "param=input_image" in detail
    assert _SECRET not in detail
    assert "SECRETIMAGE" not in detail
    lines = _upstream_lines(caplog)
    assert len(lines) == 1
    assert "code=internal_error" in lines[0]
    assert "type=server_error" in lines[0]
    assert "param=input_image" in lines[0]
    assert "transient_retry=True" in lines[0]
    assert "phase=upstream" in lines[0]
    assert _SECRET not in lines[0]
    assert "SECRETIMAGE" not in lines[0]
    assert "\n" not in lines[0]


@pytest.mark.asyncio
async def test_response_protection_switches_account_after_same_account_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _StreamHarness(monkeypatch, ["acc_protection_a", "acc_protection_b"])
    account_a = harness.accounts[0].chatgpt_account_id
    account_b = harness.accounts[1].chatgpt_account_id
    harness.install_stream(
        monkeypatch,
        {
            account_a: [[_protection_error()], [_protection_error()], [_protection_error()]],
            account_b: [[_completed("resp_protection_b")]],
        },
    )

    chunks = await harness.stream(request_id="req_protection_switch")

    events = _events(chunks)
    assert [event["type"] for event in events] == ["response.completed"]
    assert harness.stream_accounts == [account_a, account_a, account_a, account_b]
    assert harness.accounts[0].id in harness.seen_excluded[-1]
    assert await harness.service.drain_persistence_tasks(timeout_seconds=1)
    assert [call["status"] for call in harness.request_logs.calls] == ["error", "error", "error", "success"]
    assert {call["upstream_error_code"] for call in harness.request_logs.calls if call["status"] == "error"} == {
        "internal_error"
    }


@pytest.mark.asyncio
async def test_response_protection_after_created_does_not_forward_the_failed_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _StreamHarness(monkeypatch, ["acc_protection_created"])
    account_id = harness.accounts[0].chatgpt_account_id
    harness.install_stream(
        monkeypatch,
        {
            account_id: [
                [_created("resp_held"), _protection_error()],
                [_completed("resp_after_held")],
            ]
        },
    )

    chunks = await harness.stream(request_id="req_protection_held")
    body = "".join(chunks)

    assert "resp_held" not in body
    assert _MESSAGE not in body
    assert "resp_after_held" in body
    assert harness.stream_accounts == [account_id, account_id]


@pytest.mark.asyncio
async def test_response_protection_after_output_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING", logger="app.modules.proxy.service")
    harness = _StreamHarness(monkeypatch, ["acc_protection_visible", "acc_protection_unused"])
    account_id = harness.accounts[0].chatgpt_account_id
    harness.install_stream(
        monkeypatch,
        {account_id: [[_text_delta("visible"), _protection_error()]]},
    )

    chunks = await harness.stream(request_id="req_protection_visible")
    events = _events(chunks)

    assert [event["type"] for event in events] == ["response.output_text.delta", "error"]
    assert events[1]["error"]["code"] == "internal_error"
    assert events[1]["error"]["message"] == _MESSAGE
    assert harness.stream_accounts == [account_id]
    assert all(harness.accounts[0].id not in excluded for excluded in harness.seen_excluded)
    lines = _upstream_lines(caplog)
    assert len(lines) == 1
    assert "transient_retry=False" in lines[0]


@pytest.mark.asyncio
async def test_other_internal_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _StreamHarness(monkeypatch, ["acc_protection_other", "acc_protection_other_b"])
    account_id = harness.accounts[0].chatgpt_account_id
    harness.install_stream(
        monkeypatch,
        {account_id: [[_protection_error(message="upstream exploded", param=None)]]},
    )

    chunks = await harness.stream(request_id="req_protection_other")
    events = _events(chunks)

    assert [event["type"] for event in events] == ["error"]
    assert events[0]["error"]["message"] == "upstream exploded"
    assert harness.stream_accounts == [account_id]
    assert await harness.service.drain_persistence_tasks(timeout_seconds=1)
    failed = harness.request_logs.calls[0]
    assert failed["upstream_error_code"] == "internal_error"
    assert failed["failure_phase"] == "upstream"
    assert "upstream exploded" in str(failed["failure_detail"])
    assert "type=server_error" in str(failed["failure_detail"])


@pytest.mark.asyncio
async def test_image_bypass_success_is_stored_under_archive_request_id(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="app.modules.proxy.service")
    harness = _StreamHarness(monkeypatch, ["acc_image_bypass"])
    account_id = harness.accounts[0].chatgpt_account_id
    harness.settings.http_responses_stream_request_budget_seconds = 180.0
    monkeypatch.setattr(
        proxy_service,
        "_http_bridge_runtime_config",
        lambda _dashboard_settings, _app_settings: proxy_service._HTTPBridgeRuntimeConfig(
            enabled=True,
            idle_ttl_seconds=30.0,
            codex_idle_ttl_seconds=30.0,
            max_sessions=8,
            queue_limit=16,
            prompt_cache_idle_ttl_seconds=30.0,
            gateway_safe_mode=False,
        ),
    )
    monkeypatch.setattr(harness.service, "_resolve_file_account_for_responses", AsyncMock(return_value=None))
    harness.install_stream(monkeypatch, {account_id: [[_completed("resp_image_bypass")]]})
    payload = ResponsesRequest.model_validate(
        {
            "model": "gpt-5.6-sol",
            "instructions": "hi",
            "input": _image_input(),
            "stream": True,
        }
    )
    token = set_request_id("req_image_bypass_lookup")
    try:
        chunks = [
            chunk
            async for chunk in harness.service.stream_http_responses(
                payload,
                {"session_id": "sid-image", "authorization": _SECRET},
            )
        ]
    finally:
        reset_request_id(token)

    assert _events(chunks)[0]["response"]["id"] == "resp_image_bypass"
    bypass_lines = [
        record.getMessage()
        for record in caplog.records
        if "bypassing http bridge for image-capable request" in record.getMessage()
    ]
    assert len(bypass_lines) == 1
    assert "request_id=req_image_bypass_lookup" in bypass_lines[0]
    assert await harness.service.drain_persistence_tasks(timeout_seconds=1)
    assert len(harness.request_logs.calls) == 1
    saved = harness.request_logs.calls[0]
    assert saved["status"] == "success"
    assert saved["request_id"] == "resp_image_bypass"
    assert saved["archive_request_id"] == "req_image_bypass_lookup"
