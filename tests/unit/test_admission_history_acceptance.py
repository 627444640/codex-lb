"""Acceptance fixes: one shared retry, SSE cuts, and cached failover."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anyio
import pytest

from app.modules.proxy import service as proxy_service
from app.modules.proxy._load_balancer.admission_breaker import (
    AdmissionBreakerPolicy,
    AdmissionFailoverAction,
    mark_transparent_retry,
    plan_admission_failover,
    record_admission_failure_locked,
    record_upstream_admission_failure,
    reset_admission_failure_dedupe,
    transparent_retry_used,
)
from app.modules.proxy._load_balancer.types import RuntimeState
from app.modules.proxy._service.streaming.retry import _http_stream_admission_plan
from app.modules.proxy._service.support import (
    _RetryableStreamError,
    _stage_websocket_history_replay,
    _StreamSettlement,
    _WebSocketRequestState,
)
from app.modules.proxy.conversation_history import (
    ConversationHistoryCache,
    reset_history_replay_context,
)


def _cache(tmp_path):
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


def test_open_breaker_does_not_extend_for_in_flight_failures() -> None:
    runtime = RuntimeState()
    policy = AdmissionBreakerPolicy(failure_threshold=1, window_seconds=60, open_seconds=300)
    assert record_admission_failure_locked(runtime, 1_000.0, policy, account_id="a") is True
    opened = runtime.admission_open_until
    assert record_admission_failure_locked(runtime, 1_050.0, policy, account_id="a") is False
    assert runtime.admission_open_until == opened


def test_half_open_transition_logs_once(caplog: pytest.LogCaptureFixture) -> None:
    runtime = RuntimeState(admission_open_until=1_000.0)
    policy = AdmissionBreakerPolicy()
    with caplog.at_level(logging.INFO):
        from app.modules.proxy._load_balancer.admission_breaker import admission_phase

        assert admission_phase(runtime, 1_001.0, policy) == "half_open"
        assert admission_phase(runtime, 1_002.0, policy) == "half_open"
    assert sum("half-open" in message for message in caplog.messages) == 1


def test_sse_stream_incomplete_without_close_code_can_fail_over() -> None:
    action = _http_stream_admission_plan(
        error_code="stream_incomplete",
        http_status=None,
        error_message="Upstream stream ended before response.completed",
        downstream_visible=False,
        already_retried=False,
        continuity_pinned=False,
        attempts_remaining=True,
    )
    assert action == AdmissionFailoverAction.FAILOVER_ONCE
    pinned = _http_stream_admission_plan(
        error_code="stream_incomplete",
        http_status=None,
        error_message="Upstream stream ended before response.completed",
        downstream_visible=True,
        already_retried=False,
        continuity_pinned=False,
        attempts_remaining=True,
    )
    assert pinned == AdmissionFailoverAction.PASSTHROUGH


async def test_one_stream_incomplete_is_counted_once() -> None:
    class _Account:
        id = "acct"

    class _Balancer:
        def __init__(self) -> None:
            self._runtime: dict[str, RuntimeState] = {}

        async def _get_account_lock(self, account_id: str) -> asyncio.Lock:
            del account_id
            return asyncio.Lock()

    reset_admission_failure_dedupe()
    balancer = _Balancer()
    await record_upstream_admission_failure(
        balancer,
        _Account(),
        error_code="stream_incomplete",
        pre_first_output_close=True,
    )
    await record_upstream_admission_failure(
        balancer,
        _Account(),
        error_code="stream_incomplete",
        pre_first_output_close=True,
    )
    runtime = balancer._runtime["acct"]
    assert runtime.admission_consecutive_failures == 1
    reset_admission_failure_dedupe()
    await record_upstream_admission_failure(
        balancer,
        _Account(),
        error_code="stream_incomplete",
        pre_first_output_close=True,
    )
    assert runtime.admission_consecutive_failures == 2


def test_admission_failure_uses_cached_history_and_consumes_the_shared_retry(tmp_path) -> None:
    cache = _cache(tmp_path)
    body = {
        "model": "gpt-6-astra",
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "kept"}]}],
        "previous_response_id": None,
    }
    cache.record_completed_turn(
        request_body=body,
        response_id="resp-1",
        output_items=[{"type": "message", "text": "ok"}],
    )
    reset_history_replay_context()
    from app.modules.proxy._load_balancer.admission_breaker import _transparent_retry_used

    token = _transparent_retry_used.set(False)
    try:
        replay = cache.plan_replay(
            request_body={
                "model": "gpt-6-astra",
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "next"}]}],
                "previous_response_id": "resp-1",
            },
            reason="admission_failure",
            downstream_visible=False,
            already_replayed=False,
            owner_blocked=True,
            file_pinned=False,
        )
        assert replay is not None
        assert replay.switch_account is True
        assert "previous_response_id" not in replay.request_body
        assert transparent_retry_used() is True
        assert (
            cache.plan_replay(
                request_body={
                    "model": "gpt-6-astra",
                    "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "next"}]}],
                    "previous_response_id": "resp-1",
                },
                reason="stream_incomplete",
                downstream_visible=False,
                already_replayed=False,
                owner_blocked=False,
                file_pinned=False,
            )
            is None
        )
        assert (
            plan_admission_failover(
                error_code="server_error",
                http_status=500,
                downstream_visible=False,
                already_retried=transparent_retry_used(),
                continuity_pinned=False,
                attempts_remaining=True,
                pre_first_output_close=False,
            )
            == AdmissionFailoverAction.SURFACE
        )
    finally:
        _transparent_retry_used.reset(token)
        cache.close()


def test_admission_failover_blocks_a_later_history_replay(tmp_path) -> None:
    cache = _cache(tmp_path)
    reset_history_replay_context()
    from app.modules.proxy._load_balancer.admission_breaker import _transparent_retry_used

    token = _transparent_retry_used.set(False)
    try:
        mark_transparent_retry()
        assert (
            cache.plan_replay(
                request_body={
                    "model": "gpt-6-astra",
                    "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "next"}]}],
                    "previous_response_id": "resp-1",
                },
                reason="previous_response_not_found",
                downstream_visible=False,
                already_replayed=False,
                owner_blocked=False,
                file_pinned=False,
            )
            is None
        )
    finally:
        _transparent_retry_used.reset(token)
        cache.close()


def test_websocket_admission_failure_stages_cached_history(tmp_path) -> None:
    cache = _cache(tmp_path)
    from app.modules.proxy import conversation_history as history_module
    from app.modules.proxy._load_balancer.admission_breaker import _transparent_retry_used

    history_module.set_conversation_history_cache(cache)
    body = {
        "model": "gpt-6-astra",
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "kept"}]}],
    }
    cache.record_completed_turn(request_body=body, response_id="resp-1", output_items=[{"type": "message"}])
    reset_history_replay_context()
    token = _transparent_retry_used.set(False)
    state = _WebSocketRequestState(
        request_id="req-ws",
        model="gpt-6-astra",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=0.0,
        request_text='{"model":"gpt-6-astra","input":[{"type":"message","role":"user","content":[{"type":"input_text","text":"more"}]}],"previous_response_id":"resp-1"}',
        previous_response_id="resp-1",
        preferred_account_id=None,
    )
    try:
        assert _stage_websocket_history_replay(
            state,
            account_id="acct",
            reason="admission_failure",
            owner_blocked=True,
        )
        assert state.previous_response_id is None
        assert "acct" in state.excluded_account_ids
        assert transparent_retry_used() is True
    finally:
        _transparent_retry_used.reset(token)
        history_module.set_conversation_history_cache(None)
        cache.close()


async def test_http_500_with_previous_response_replays_from_cache(tmp_path) -> None:
    cache = _cache(tmp_path)
    from app.modules.proxy import conversation_history as history_module
    from app.modules.proxy._load_balancer.admission_breaker import _transparent_retry_used
    from app.modules.proxy._service.streaming.helpers import _replay_http_history

    history_module.set_conversation_history_cache(cache)
    cache.record_completed_turn(
        request_body={
            "model": "gpt-6-astra",
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "kept"}]}],
        },
        response_id="resp-1",
        output_items=[{"type": "message"}],
    )
    reset_history_replay_context()
    token = _transparent_retry_used.set(False)

    class _Payload:
        def __init__(self) -> None:
            self.input = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "more"}]}]
            self.previous_response_id: str | None = "resp-1"
            self.conversation = "conv"

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {
                "model": "gpt-6-astra",
                "input": self.input,
                "previous_response_id": self.previous_response_id,
                "conversation": self.conversation,
            }

    payload = _Payload()
    try:
        with pytest.raises(_RetryableStreamError) as raised:
            await _replay_http_history(
                object(),
                payload,
                type("A", (), {"id": "acct"})(),
                _StreamSettlement(),
                "req-http",
                True,
                "server_error",
                ("server_error", None, "overloaded"),
            )
        assert raised.value.exclude_account is True
        assert payload.previous_response_id is None
        assert transparent_retry_used() is True
    finally:
        _transparent_retry_used.reset(token)
        history_module.set_conversation_history_cache(None)
        cache.close()


def _bridge_session(request_state: _WebSocketRequestState) -> object:
    return proxy_service._HTTPBridgeSession(
        key=proxy_service._HTTPBridgeSessionKey("prompt_cache", "bridge-key", None),
        headers={},
        affinity=proxy_service._AffinityPolicy(),
        request_model="gpt-6-astra",
        account=SimpleNamespace(id="acct-bridge"),
        upstream=AsyncMock(),
        upstream_control=proxy_service._WebSocketUpstreamControl(),
        pending_requests=deque([request_state]),
        pending_lock=anyio.Lock(),
        response_create_gate=asyncio.Semaphore(1),
        queued_request_count=1,
        last_used_at=0.0,
        idle_ttl_seconds=30.0,
        last_upstream_close_code=None,
    )


def _bridge_request(text: str) -> _WebSocketRequestState:
    return _WebSocketRequestState(
        request_id="req-bridge",
        model="gpt-6-astra",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=0.0,
        response_create_sent_at=0.0,
        awaiting_response_created=True,
        request_text=text,
        previous_response_id="resp-1",
        transport="http",
        error_code_override="server_error",
        account_response_create_lease=object(),
    )


async def test_http_bridge_500_replays_cached_history_onto_another_account(tmp_path, monkeypatch) -> None:
    cache = _cache(tmp_path)
    from app.modules.proxy import conversation_history as history_module

    history_module.set_conversation_history_cache(cache)
    cache.record_completed_turn(
        request_body={
            "model": "gpt-6-astra",
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "kept"}]}],
        },
        response_id="resp-1",
        output_items=[{"type": "message"}],
    )
    reset_history_replay_context()
    request_state = _bridge_request(
        json.dumps(
            {
                "model": "gpt-6-astra",
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "more"}]}],
                "previous_response_id": "resp-1",
            }
        )
    )
    sent: list[str] = []

    async def capture_send(_session: object, _request_state: object, text: str) -> None:
        sent.append(text)

    service = proxy_service.ProxyService(lambda: None)
    monkeypatch.setattr(service, "_reconnect_http_bridge_session", AsyncMock())
    monkeypatch.setattr(
        service,
        "_http_bridge_text_with_account_installation_id",
        lambda _session, _request_state, text: text,
    )
    monkeypatch.setattr(
        "app.modules.proxy._service.http_bridge.request_submit._send_http_bridge_request_text_with_archive_id",
        capture_send,
    )
    try:
        retried = await service._retry_http_bridge_precreated_request(
            _bridge_session(request_state),
            request_state=request_state,
        )
    finally:
        history_module.set_conversation_history_cache(None)
        cache.close()
    assert retried is True
    assert request_state.previous_response_id is None
    assert "acct-bridge" in request_state.excluded_account_ids
    assert sent
    assert "previous_response_id" not in json.loads(sent[0])


async def test_http_bridge_without_cache_does_not_switch_with_the_original_id(tmp_path, monkeypatch) -> None:
    cache = _cache(tmp_path)
    from app.modules.proxy import conversation_history as history_module

    history_module.set_conversation_history_cache(cache)
    reset_history_replay_context()
    request_state = _bridge_request('{"model":"gpt-6-astra","input":"more","previous_response_id":"resp-1"}')
    service = proxy_service.ProxyService(lambda: None)
    monkeypatch.setattr(service, "_reconnect_http_bridge_session", AsyncMock())
    try:
        retried = await service._retry_http_bridge_precreated_request(
            _bridge_session(request_state),
            request_state=request_state,
        )
    finally:
        history_module.set_conversation_history_cache(None)
        cache.close()
    assert retried is False
    assert request_state.previous_response_id == "resp-1"
    assert "acct-bridge" not in request_state.excluded_account_ids
