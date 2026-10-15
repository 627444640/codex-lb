from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.core.openai.requests import ResponsesRequest
from app.core.types import JsonValue
from app.core.utils.request_id import reset_request_id, set_request_id
from app.db.models import Account
from app.modules.proxy import conversation_history as history_module
from app.modules.proxy import service as proxy_service
from app.modules.proxy._service.streaming import helpers as streaming_helpers
from app.modules.proxy.conversation_history import ConversationHistoryCache
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
_SAME_ACCOUNT_LIMIT = proxy_service._MAX_TRANSIENT_SAME_ACCOUNT_RETRIES
_CACHED_USER = "cached-user-turn-alpha"
_CACHED_ASSISTANT = "cached-assistant-beta"


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
        self.upstream_payloads: list[dict[str, Any]] = []
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
            dump = getattr(_payload, "model_dump", None)
            if callable(dump):
                self.upstream_payloads.append(dump(mode="json"))
            attempts = script[account_id]
            index = cursors[account_id]
            cursors[account_id] = index + 1
            for line in attempts[index]:
                yield line

        monkeypatch.setattr(proxy_service, "core_stream_responses", fake_stream)

    def enable_image_http_sse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.settings.http_responses_stream_request_budget_seconds = 180.0
        monkeypatch.setattr(
            "app.modules.proxy._service.http_bridge.streaming._http_bridge_runtime_config",
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
        monkeypatch.setattr(self.service, "_resolve_file_account_for_responses", AsyncMock(return_value=None))

    async def stream(
        self,
        *,
        request_id: str,
        input_value: object | None = None,
        extra: Mapping[str, object] | None = None,
        http_sse: bool = False,
    ) -> list[str]:
        body: dict[str, object] = {
            "model": "gpt-5.6-sol",
            "instructions": "hi",
            "input": input_value if input_value is not None else [],
            "stream": True,
        }
        if extra is not None:
            body.update(dict(extra))
        payload = ResponsesRequest.model_validate(body)
        token = set_request_id(request_id)
        try:
            source = self.service.stream_http_responses if http_sse else self.service.stream_responses
            return [
                chunk
                async for chunk in source(
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


def _client_error(events: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [event for event in events if event.get("type") == "response.failed"]
    assert len(failed) == 1
    error = failed[0]["response"]["error"]
    assert isinstance(error, dict)
    return error


def _overloaded_after_created() -> list[str]:
    return [
        _created("resp_admission_hold"),
        _sse(
            {
                "type": "error",
                "error": {
                    "code": "overloaded_error",
                    "message": "The server is overloaded.",
                    "type": "server_error",
                },
            }
        ),
    ]


def _history_cache(tmp_path: Path) -> ConversationHistoryCache:
    cache = ConversationHistoryCache(
        tmp_path / "conversation_history.db",
        enabled=True,
        max_bytes=1024**3,
        conversation_max_bytes=32 * 1024 * 1024,
        idle_ttl_seconds=1800,
        min_free_disk_bytes=0,
        batch_limit=1,
        start_maintenance=False,
        disk_free=10**12,
    )
    history_module.set_conversation_history_cache(cache)
    return cache


def _record_cached_turn(cache: ConversationHistoryCache, response_id: str) -> None:
    body: dict[str, JsonValue] = {
        "model": "gpt-5.6-sol",
        "instructions": "hi",
        "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": _CACHED_USER}]},
        ],
    }
    cache.record_completed_turn(
        request_body=body,
        response_id=response_id,
        output_items=[
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": _CACHED_ASSISTANT}],
            }
        ],
    )
    cache.flush()


@pytest.mark.asyncio
async def test_response_protection_second_account_failure_does_not_switch_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _StreamHarness(
        monkeypatch,
        ["acc_protection_bound_a", "acc_protection_bound_b", "acc_protection_bound_c"],
    )
    account_a = harness.accounts[0].chatgpt_account_id
    account_b = harness.accounts[1].chatgpt_account_id
    account_c = harness.accounts[2].chatgpt_account_id
    harness.install_stream(
        monkeypatch,
        {
            account_a: [[_protection_error()] for _ in range(_SAME_ACCOUNT_LIMIT)],
            account_b: [[_protection_error()] for _ in range(_SAME_ACCOUNT_LIMIT)],
            account_c: [[_completed("resp_protection_should_not_run")]],
        },
    )

    chunks = await harness.stream(request_id="req_protection_one_switch")
    body = "".join(chunks)
    error = _client_error(_events(chunks))

    assert error["code"] == "internal_error"
    assert error["message"] == _MESSAGE
    assert "resp_protection_should_not_run" not in body
    assert account_c not in harness.stream_accounts
    assert harness.stream_accounts[0] == account_a
    assert account_b in harness.stream_accounts
    assert set(harness.stream_accounts) == {account_a, account_b}
    assert harness.stream_accounts.count(account_a) <= _SAME_ACCOUNT_LIMIT
    assert harness.stream_accounts.count(account_b) <= _SAME_ACCOUNT_LIMIT
    # Same-account retries on the original account, plus the same budget on the one switched account.
    assert len(harness.stream_accounts) <= _SAME_ACCOUNT_LIMIT * 2


@pytest.mark.asyncio
async def test_response_protection_does_not_switch_after_admission_failover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _StreamHarness(
        monkeypatch, ["acc_protection_after_a", "acc_protection_after_b", "acc_protection_after_c"]
    )
    account_a = harness.accounts[0].chatgpt_account_id
    account_b = harness.accounts[1].chatgpt_account_id
    account_c = harness.accounts[2].chatgpt_account_id
    harness.install_stream(
        monkeypatch,
        {
            account_a: [_overloaded_after_created()],
            account_b: [[_protection_error()] for _ in range(_SAME_ACCOUNT_LIMIT)],
            account_c: [[_completed("resp_protection_after_budget")]],
        },
    )

    chunks = await harness.stream(request_id="req_protection_after_admission")
    body = "".join(chunks)
    error = _client_error(_events(chunks))

    assert error["code"] == "internal_error"
    assert error["message"] == _MESSAGE
    assert "resp_protection_after_budget" not in body
    assert "resp_admission_hold" not in body
    assert harness.stream_accounts[0] == account_a
    assert account_c not in harness.stream_accounts
    assert set(harness.stream_accounts) == {account_a, account_b}
    assert harness.stream_accounts.count(account_a) == 1
    assert harness.stream_accounts.count(account_b) <= _SAME_ACCOUNT_LIMIT
    assert len(harness.stream_accounts) <= 1 + _SAME_ACCOUNT_LIMIT


@pytest.mark.asyncio
async def test_image_previous_response_switch_replays_cached_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="app.modules.proxy.service")
    cache = _history_cache(tmp_path)
    try:
        _record_cached_turn(cache, "resp_cached_owner")
        harness = _StreamHarness(monkeypatch, ["acc_protection_replay_a", "acc_protection_replay_b"])
        harness.enable_image_http_sse(monkeypatch)
        account_a = harness.accounts[0].chatgpt_account_id
        account_b = harness.accounts[1].chatgpt_account_id
        monkeypatch.setattr(
            harness.service,
            "_resolve_websocket_previous_response_owner",
            AsyncMock(return_value=harness.accounts[0].id),
        )
        harness.install_stream(
            monkeypatch,
            {
                account_a: [[_protection_error()] for _ in range(_SAME_ACCOUNT_LIMIT)],
                account_b: [[_completed("resp_protection_replayed")]],
            },
        )

        chunks = await harness.stream(
            request_id="req_protection_replay",
            input_value=_image_input(),
            extra={"previous_response_id": "resp_cached_owner"},
            http_sse=True,
        )
    finally:
        history_module.set_conversation_history_cache(None)

    events = _events(chunks)
    assert [event["type"] for event in events] == ["response.completed"]
    assert events[0]["response"]["id"] == "resp_protection_replayed"
    assert harness.stream_accounts[:_SAME_ACCOUNT_LIMIT] == [account_a] * _SAME_ACCOUNT_LIMIT
    assert harness.stream_accounts[_SAME_ACCOUNT_LIMIT:] == [account_b]
    owner_payloads = harness.upstream_payloads[:_SAME_ACCOUNT_LIMIT]
    moved = harness.upstream_payloads[_SAME_ACCOUNT_LIMIT]
    assert all(payload["previous_response_id"] == "resp_cached_owner" for payload in owner_payloads)
    assert "previous_response_id" not in moved or moved["previous_response_id"] is None
    moved_input = json.dumps(moved["input"])
    assert _CACHED_USER in moved_input
    assert _CACHED_ASSISTANT in moved_input
    assert "input_image" in moved_input
    assert any("bypassing http bridge for image-capable request" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_image_previous_response_cache_miss_stays_on_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="app.modules.proxy.service")
    _history_cache(tmp_path)
    try:
        harness = _StreamHarness(
            monkeypatch,
            ["acc_protection_miss_a", "acc_protection_miss_b", "acc_protection_miss_c"],
        )
        harness.enable_image_http_sse(monkeypatch)
        account_a = harness.accounts[0].chatgpt_account_id
        account_b = harness.accounts[1].chatgpt_account_id
        account_c = harness.accounts[2].chatgpt_account_id
        monkeypatch.setattr(
            harness.service,
            "_resolve_websocket_previous_response_owner",
            AsyncMock(return_value=harness.accounts[0].id),
        )
        harness.install_stream(
            monkeypatch,
            {
                account_a: [[_protection_error()] for _ in range(_SAME_ACCOUNT_LIMIT)],
                account_b: [[_completed("resp_protection_miss_moved")]],
                account_c: [[_completed("resp_protection_miss_third")]],
            },
        )

        chunks = await harness.stream(
            request_id="req_protection_cache_miss",
            input_value=_image_input(),
            extra={"previous_response_id": "resp_not_cached"},
            http_sse=True,
        )
    finally:
        history_module.set_conversation_history_cache(None)

    error = _client_error(_events(chunks))
    body = "".join(chunks)
    assert error["code"] == "internal_error"
    assert error["message"] == _MESSAGE
    assert "resp_protection_miss_moved" not in body
    assert "resp_protection_miss_third" not in body
    assert harness.stream_accounts == [account_a] * _SAME_ACCOUNT_LIMIT
    assert account_b not in harness.stream_accounts
    assert account_c not in harness.stream_accounts
    assert all(payload["previous_response_id"] == "resp_not_cached" for payload in harness.upstream_payloads)
    assert len(harness.stream_accounts) <= _SAME_ACCOUNT_LIMIT
    assert any("bypassing http bridge for image-capable request" in record.getMessage() for record in caplog.records)
