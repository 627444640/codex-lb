"""HTTP bridge previous_response_not_found resends from the history cache."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Iterator
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import anyio
import pytest

from app.core.clients.proxy_websocket import UpstreamWebSocket
from app.core.config.settings import Settings
from app.core.types import JsonValue
from app.db.models import AccountStatus
from app.modules.proxy import service as proxy_service
from app.modules.proxy._service.support import _websocket_request_log_retry_marks
from app.modules.proxy._service.websocket.helpers import (
    _clear_websocket_stale_previous_response_cache,
    _is_websocket_stale_previous_response,
    _websocket_stale_anchor_diagnostics,
)
from app.modules.proxy.conversation_history import (
    ConversationHistoryCache,
    reset_history_replay_context,
    set_conversation_history_cache,
)

pytestmark = pytest.mark.unit


def _cache(tmp_path) -> ConversationHistoryCache:
    return ConversationHistoryCache(
        tmp_path / "conversation_history.db",
        enabled=True,
        max_bytes=1024**3,
        conversation_max_bytes=32 * 1024 * 1024,
        idle_ttl_seconds=1800,
        min_free_disk_bytes=1,
        start_maintenance=False,
        disk_free=10 * 1024**3,
    )


@pytest.fixture
def history_cache(tmp_path) -> Iterator[ConversationHistoryCache]:
    cache = _cache(tmp_path)
    set_conversation_history_cache(cache)
    reset_history_replay_context()
    _clear_websocket_stale_previous_response_cache()
    try:
        yield cache
    finally:
        reset_history_replay_context()
        _clear_websocket_stale_previous_response_cache()
        set_conversation_history_cache(None)


def _seed_history(cache: ConversationHistoryCache) -> None:
    cache.record_completed_turn(
        request_body={
            "model": "gpt-5.4",
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "kept"}]}],
        },
        response_id="resp-1",
        output_items=[{"type": "message", "text": "ok"}],
    )


def _anchored_create_text() -> str:
    return json.dumps(
        {
            "type": "response.create",
            "model": "gpt-5.4",
            "previous_response_id": "resp-1",
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "more"}]}],
        },
        separators=(",", ":"),
    )


def _prnf_text(*, response_id: str | None = None) -> str:
    error: dict[str, JsonValue] = {
        "type": "invalid_request_error",
        "code": "previous_response_not_found",
        "message": "Previous response with id 'resp-1' not found.",
        "param": "previous_response_id",
    }
    if response_id is None:
        payload: dict[str, JsonValue] = {"type": "error", "status": 400, "error": error}
    else:
        payload = {
            "type": "response.failed",
            "response": {"id": response_id, "status": "failed", "error": error},
        }
    return json.dumps(payload, separators=(",", ":"))


def _anchored_request() -> proxy_service._WebSocketRequestState:
    return proxy_service._WebSocketRequestState(
        request_id="req-http-prnf",
        model="gpt-5.4",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=time.monotonic(),
        awaiting_response_created=True,
        request_text=_anchored_create_text(),
        previous_response_id="resp-1",
        hard_continuity_anchor=True,
        event_queue=asyncio.Queue(),
        transport="http",
        skip_request_log=True,
    )


def _session(
    request_state: proxy_service._WebSocketRequestState,
) -> tuple[proxy_service._HTTPBridgeSession, AsyncMock]:
    send_text = AsyncMock()
    session = proxy_service._HTTPBridgeSession(
        key=proxy_service._HTTPBridgeSessionKey("session_header", "sid-http-prnf", None),
        headers={"x-codex-session-id": "sid-http-prnf"},
        affinity=proxy_service._AffinityPolicy(
            key="sid-http-prnf",
            kind=proxy_service.StickySessionKind.CODEX_SESSION,
        ),
        request_model="gpt-5.4",
        account=cast(Any, SimpleNamespace(id="acc-http-prnf", status=AccountStatus.ACTIVE)),
        upstream=cast(UpstreamWebSocket, SimpleNamespace(send_text=send_text, close=AsyncMock())),
        upstream_control=proxy_service._WebSocketUpstreamControl(),
        pending_requests=deque([request_state]),
        pending_lock=anyio.Lock(),
        response_create_gate=asyncio.Semaphore(1),
        queued_request_count=1,
        last_used_at=1.0,
        idle_ttl_seconds=120.0,
    )
    return session, send_text


class _SettingsCache:
    async def get(self) -> Settings:
        return Settings(http_responses_session_bridge_enabled=True)


def _patch_bridge_retry(monkeypatch: pytest.MonkeyPatch, service: Any) -> AsyncMock:
    monkeypatch.setattr(
        "app.modules.proxy._service.http_bridge.upstream_events.admission_retry_jitter_seconds",
        lambda: 0.0,
    )
    settings = Settings(http_responses_session_bridge_enabled=True)
    monkeypatch.setattr(proxy_service, "get_settings", lambda: settings)
    monkeypatch.setattr(proxy_service, "get_settings_cache", lambda: _SettingsCache())
    monkeypatch.setattr(service, "_load_http_bridge_retry_circuit", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())
    reconnect = AsyncMock()
    monkeypatch.setattr(service, "_reconnect_http_bridge_session", reconnect)
    monkeypatch.setattr(
        service,
        "_acquire_account_response_create_lease_or_overload",
        AsyncMock(return_value=SimpleNamespace(id="lease-http-prnf")),
    )
    return reconnect


def _queued_payloads(request_state: proxy_service._WebSocketRequestState) -> list[dict[str, Any]]:
    event_queue = request_state.event_queue
    assert event_queue is not None
    payloads: list[dict[str, Any]] = []
    while not event_queue.empty():
        block = event_queue.get_nowait()
        if block is None:
            continue
        parsed = proxy_service.parse_sse_data_json(block)
        assert isinstance(parsed, dict)
        payloads.append(cast(dict[str, Any], parsed))
    return payloads


def _assert_fail_closed_terminal(payload: dict[str, Any]) -> None:
    assert payload["type"] == "response.failed"
    response = payload["response"]
    assert isinstance(response, dict)
    error = response["error"]
    assert isinstance(error, dict)
    assert error["code"] == "stream_incomplete"
    assert error["message"] == "Upstream websocket closed before response.completed"
    assert "previous_response_not_found" not in json.dumps(payload)


def _fail_closed_logged(caplog: pytest.LogCaptureFixture) -> bool:
    return any(
        "continuity_fail_closed" in record.getMessage() and "reason=previous_response_not_found" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [False, True], ids=["pre-created", "accepted"])
async def test_http_bridge_previous_response_not_found_resends_cached_history_once(
    history_cache: ConversationHistoryCache,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    accepted: bool,
) -> None:
    _seed_history(history_cache)
    caplog.set_level(logging.WARNING)
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    request_state = _anchored_request()
    session, send_text = _session(request_state)
    reconnect = _patch_bridge_retry(monkeypatch, service)

    if accepted:
        await service._process_http_bridge_upstream_text(
            session,
            json.dumps(
                {"type": "response.created", "response": {"id": "resp_x", "status": "in_progress"}},
                separators=(",", ":"),
            ),
        )

    await service._process_http_bridge_upstream_text(
        session,
        _prnf_text(response_id="resp_x" if accepted else None),
    )

    send_text.assert_awaited_once()
    sent = json.loads(send_text.await_args.args[0])
    assert "previous_response_id" not in sent
    sent_input = json.dumps(sent["input"])
    assert "kept" in sent_input
    assert "more" in sent_input
    assert request_state.history_replay_used is True
    assert request_state.previous_response_id is None
    assert request_state.replay_count == 1
    marks = _websocket_request_log_retry_marks(request_state)
    assert marks.history_replay is not None
    assert marks.history_replay.reason == "previous_response_not_found"
    assert request_state in session.pending_requests
    assert session.queued_request_count == 1
    assert not _fail_closed_logged(caplog)
    assert request_state.failure_detail_override is None
    service._handle_stream_error.assert_not_awaited()
    reconnect.assert_awaited_once()
    assert reconnect.await_args is not None
    assert reconnect.await_args.kwargs["require_same_account"] is True
    assert "acc-http-prnf" not in request_state.excluded_account_ids
    delivered = _queued_payloads(request_state)
    assert all(payload.get("type") != "response.failed" for payload in delivered)
    if accepted:
        assert request_state.replay_downstream_response_id == "resp_x"
        assert request_state.suppress_next_created_downstream is True
        assert [payload["type"] for payload in delivered] == ["response.created"]
    else:
        assert delivered == []


@pytest.mark.asyncio
async def test_http_bridge_previous_response_not_found_without_cache_returns_original_error(
    history_cache: ConversationHistoryCache,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    del history_cache
    caplog.set_level(logging.WARNING)
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    request_state = _anchored_request()
    session, _send_text = _session(request_state)
    retry = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "_retry_http_bridge_precreated_request", retry)
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())

    await service._process_http_bridge_upstream_text(session, _prnf_text())

    retry.assert_not_awaited()
    assert request_state.history_replay_used is False
    assert request_state.replay_count == 0
    assert request_state.previous_response_not_found_rewritten is True
    assert request_state.failure_detail_override is not None
    assert "fresh_replay_available=false" in request_state.failure_detail_override
    assert _is_websocket_stale_previous_response(previous_response_id="resp-1", api_key_id=None)
    assert _fail_closed_logged(caplog)
    assert session.pending_requests == deque()
    assert session.queued_request_count == 0
    delivered = _queued_payloads(request_state)
    assert len(delivered) == 1
    _assert_fail_closed_terminal(delivered[0])


@pytest.mark.asyncio
async def test_http_bridge_previous_response_not_found_after_output_does_not_replay(
    history_cache: ConversationHistoryCache,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _seed_history(history_cache)
    caplog.set_level(logging.WARNING)
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    request_state = _anchored_request()
    session, _send_text = _session(request_state)
    retry = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "_retry_http_bridge_precreated_request", retry)
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())

    await service._process_http_bridge_upstream_text(
        session,
        json.dumps(
            {"type": "response.created", "response": {"id": "resp_x", "status": "in_progress"}},
            separators=(",", ":"),
        ),
    )
    await service._process_http_bridge_upstream_text(
        session,
        json.dumps(
            {"type": "response.output_text.delta", "response_id": "resp_x", "delta": "hi"},
            separators=(",", ":"),
        ),
    )
    await service._process_http_bridge_upstream_text(session, _prnf_text(response_id="resp_x"))

    retry.assert_not_awaited()
    assert request_state.history_replay_used is False
    assert request_state.downstream_visible is True
    assert request_state.failure_detail_override is not None
    assert "fresh_replay_available=true" in request_state.failure_detail_override
    assert not _is_websocket_stale_previous_response(previous_response_id="resp-1", api_key_id=None)
    assert _fail_closed_logged(caplog)
    delivered = _queued_payloads(request_state)
    assert [payload["type"] for payload in delivered] == [
        "response.created",
        "response.output_text.delta",
        "response.failed",
    ]
    _assert_fail_closed_terminal(delivered[-1])


@pytest.mark.asyncio
async def test_http_bridge_previous_response_not_found_failed_send_is_not_retried(
    history_cache: ConversationHistoryCache,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_history(history_cache)
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    request_state = _anchored_request()
    session, _send_text = _session(request_state)
    monkeypatch.setattr(
        "app.modules.proxy._service.http_bridge.upstream_events.admission_retry_jitter_seconds",
        lambda: 0.0,
    )
    retry = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "_retry_http_bridge_precreated_request", retry)
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())

    await service._process_http_bridge_upstream_text(session, _prnf_text())

    retry.assert_awaited_once()
    assert request_state.replay_count >= 1
    assert request_state.previous_response_id == "resp-1"
    assert request_state.history_replay_used is True
    assert session.pending_requests == deque()
    delivered = _queued_payloads(request_state)
    assert len(delivered) == 1
    _assert_fail_closed_terminal(delivered[0])

    session.pending_requests.append(request_state)
    session.queued_request_count = 1
    await service._process_http_bridge_upstream_text(session, _prnf_text())

    retry.assert_awaited_once()


def test_http_stale_anchor_diagnostics_count_cached_history(history_cache: ConversationHistoryCache) -> None:
    _seed_history(history_cache)
    http_request = proxy_service._WebSocketRequestState(
        request_id="req-http-diagnostic",
        model="gpt-5.4",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=0.0,
        previous_response_id="resp-1",
        transport="http",
    )
    websocket_request = proxy_service._WebSocketRequestState(
        request_id="req-ws-diagnostic",
        model="gpt-5.4",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=0.0,
        previous_response_id="resp-1",
        transport="websocket",
    )

    assert _websocket_stale_anchor_diagnostics(http_request).fresh_replay_available is True
    assert _websocket_stale_anchor_diagnostics(websocket_request).fresh_replay_available is False


def test_http_stale_anchor_diagnostics_stay_false_without_cached_history(
    history_cache: ConversationHistoryCache,
) -> None:
    del history_cache
    http_request = proxy_service._WebSocketRequestState(
        request_id="req-http-diagnostic-miss",
        model="gpt-5.4",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=0.0,
        previous_response_id="resp-1",
        transport="http",
    )

    assert _websocket_stale_anchor_diagnostics(http_request).fresh_replay_available is False
