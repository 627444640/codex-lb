"""Acceptance fixes: one shared retry, SSE cuts, and cached failover."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import anyio
import pytest

from app.core.crypto import TokenEncryptor
from app.core.types import JsonValue
from app.core.utils.time import utcnow
from app.db.models import Account, AccountStatus
from app.modules.accounts.repository import AccountsRepository
from app.modules.api_keys.repository import ApiKeysRepository
from app.modules.proxy import service as proxy_service
from app.modules.proxy._load_balancer.admission_breaker import (
    AdmissionBreakerPolicy,
    AdmissionFailoverAction,
    current_admission_failover,
    mark_transparent_retry,
    plan_admission_failover,
    record_admission_failure_locked,
    record_upstream_admission_failure,
    reset_admission_failure_dedupe,
    reset_admission_request_context,
    transparent_retry_used,
)
from app.modules.proxy._load_balancer.types import AccountLease, RuntimeState
from app.modules.proxy._service.streaming.retry import _http_stream_admission_plan
from app.modules.proxy._service.support import (
    _RetryableStreamError,
    _stage_websocket_history_replay,
    _StreamSettlement,
    _WebSocketRequestState,
)
from app.modules.proxy._service.websocket.helpers import (
    _clear_websocket_stale_previous_response_cache,
    _is_websocket_stale_previous_response,
)
from app.modules.proxy._service.websocket.mixin import _WebSocketReplaySequenceRegression
from app.modules.proxy.capability_lineage_repository import CapabilityLineageRepository
from app.modules.proxy.conversation_history import (
    ConversationHistoryCache,
    reset_history_replay_context,
)
from app.modules.proxy.repo_bundle import ProxyRepoFactory, ProxyRepositories
from app.modules.proxy.sticky_repository import StickySessionsRepository
from app.modules.request_logs.repository import RequestLogsRepository
from app.modules.usage.repository import AdditionalUsageRepository, UsageRepository


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
        staged_failover = current_admission_failover()
        assert staged_failover is not None
        assert staged_failover.from_account_id == "acct"
    finally:
        _transparent_retry_used.reset(token)
        reset_admission_request_context()
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
        failover = current_admission_failover()
        assert failover is not None
        assert failover.from_account_id == "acct"
    finally:
        _transparent_retry_used.reset(token)
        reset_admission_request_context()
        history_module.set_conversation_history_cache(None)
        cache.close()


def _bridge_session(request_state: _WebSocketRequestState) -> proxy_service._HTTPBridgeSession:
    return proxy_service._HTTPBridgeSession(
        key=proxy_service._HTTPBridgeSessionKey("prompt_cache", "bridge-key", None),
        headers={},
        affinity=proxy_service._AffinityPolicy(),
        request_model="gpt-6-astra",
        account=cast(Account, SimpleNamespace(id="acct-bridge")),
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
        account_response_create_lease=cast(AccountLease, object()),
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

    service = proxy_service.ProxyService(cast(ProxyRepoFactory, lambda: None))
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
        reset_admission_request_context()
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
    service = proxy_service.ProxyService(cast(ProxyRepoFactory, lambda: None))
    monkeypatch.setattr(service, "_reconnect_http_bridge_session", AsyncMock())
    try:
        retried = await service._retry_http_bridge_precreated_request(
            _bridge_session(request_state),
            request_state=request_state,
        )
    finally:
        reset_admission_request_context()
        history_module.set_conversation_history_cache(None)
        cache.close()
    assert retried is False
    assert request_state.previous_response_id == "resp-1"
    assert "acct-bridge" not in request_state.excluded_account_ids


class _RequestLogsRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def add_log(self, **kwargs: object) -> None:
        self.calls.append(dict(kwargs))


class _RepoContext:
    def __init__(self, request_logs: _RequestLogsRecorder) -> None:
        capability_lineage = AsyncMock(spec=CapabilityLineageRepository)
        capability_lineage.is_required.return_value = False
        self._repos = ProxyRepositories(
            accounts=cast(AccountsRepository, AsyncMock()),
            usage=cast(UsageRepository, AsyncMock()),
            request_logs=cast(RequestLogsRepository, request_logs),
            sticky_sessions=cast(StickySessionsRepository, AsyncMock()),
            api_keys=cast(ApiKeysRepository, AsyncMock()),
            additional_usage=cast(AdditionalUsageRepository, AsyncMock()),
            capability_lineage=capability_lineage,
        )

    async def __aenter__(self) -> ProxyRepositories:
        return self._repos

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


def _repo_factory(request_logs: _RequestLogsRecorder) -> ProxyRepoFactory:
    def factory() -> _RepoContext:
        return _RepoContext(request_logs)

    return factory


def _account(account_id: str) -> Account:
    encryptor = TokenEncryptor()
    now = utcnow()
    return Account(
        id=account_id,
        chatgpt_account_id=account_id,
        email=f"{account_id}@example.com",
        plan_type="plus",
        access_token_encrypted=encryptor.encrypt("access-token"),
        refresh_token_encrypted=encryptor.encrypt("refresh-token"),
        id_token_encrypted=encryptor.encrypt("id-token"),
        last_refresh=now,
        status=AccountStatus.ACTIVE,
        deactivation_reason=None,
    )


def _anchored_create_text() -> str:
    return json.dumps(
        {
            "type": "response.create",
            "model": "gpt-6-astra",
            "previous_response_id": "resp-1",
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "more"}]}],
        },
        separators=(",", ":"),
    )


def _seed_history(cache: ConversationHistoryCache) -> None:
    cache.record_completed_turn(
        request_body={
            "model": "gpt-6-astra",
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "kept"}]}],
        },
        response_id="resp-1",
        output_items=[{"type": "message", "text": "ok"}],
    )


def _accepted_anchor_state(**overrides: Any) -> _WebSocketRequestState:
    values: dict[str, Any] = {
        "request_id": "req-accepted-admission",
        "model": "gpt-6-astra",
        "service_tier": None,
        "reasoning_effort": None,
        "api_key_reservation": None,
        "started_at": 0.0,
        "response_create_sent_at": 0.0,
        "awaiting_response_created": True,
        "response_id": None,
        "response_event_count": 0,
        "response_create_gate_acquired": True,
        "request_text": _anchored_create_text(),
        "previous_response_id": "resp-1",
        "proxy_injected_previous_response_id": False,
        "preferred_account_id": "acct-a",
        "replay_required_account_id": "acct-a",
    }
    values.update(overrides)
    return _WebSocketRequestState(**values)


def _failure_payload(code: str) -> dict[str, JsonValue]:
    return {"type": "error", "error": {"type": "server_error", "code": code, "message": "upstream failed"}}


def _patch_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.proxy._load_balancer.admission_breaker.admission_retry_jitter_seconds",
        lambda: 0.0,
    )
    monkeypatch.setattr(
        "app.modules.proxy._service.websocket.mixin.admission_retry_jitter_seconds",
        lambda: 0.0,
    )
    monkeypatch.setattr(
        "app.modules.proxy._service.http_bridge.upstream_events.admission_retry_jitter_seconds",
        lambda: 0.0,
    )
    monkeypatch.setattr(
        "app.modules.proxy._service.streaming.retry.admission_retry_jitter_seconds",
        lambda: 0.0,
    )


async def _drive(
    service: Any,
    account: Account,
    pending: deque[_WebSocketRequestState],
    payload: dict[str, JsonValue],
    upstream_control: Any,
) -> str:
    return await service._process_upstream_websocket_text(
        json.dumps(payload, separators=(",", ":")),
        account=account,
        account_id_value=account.id,
        pending_requests=pending,
        pending_lock=anyio.Lock(),
        api_key=None,
        upstream_control=upstream_control,
        response_create_gate=asyncio.Semaphore(0),
    )


async def _accept(
    service: Any,
    account: Account,
    pending: deque[_WebSocketRequestState],
    upstream_control: Any,
) -> None:
    await _drive(
        service,
        account,
        pending,
        {"type": "response.created", "response": {"id": "resp_x", "status": "in_progress"}},
        upstream_control,
    )
    await _drive(
        service,
        account,
        pending,
        {"type": "response.in_progress", "response": {"id": "resp_x", "status": "in_progress"}},
        upstream_control,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["server_error", "server_is_overloaded"])
async def test_accepted_pre_output_admission_failure_replays_cached_history_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    cache = _cache(tmp_path)
    from app.modules.proxy import conversation_history as history_module

    history_module.set_conversation_history_cache(cache)
    _seed_history(cache)
    reset_history_replay_context()
    reset_admission_request_context()
    _patch_jitter(monkeypatch)
    request_logs = _RequestLogsRecorder()
    service = proxy_service.ProxyService(_repo_factory(request_logs))
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _accept(service, account, pending, upstream_control)
        await _drive(service, account, pending, _failure_payload(code), upstream_control)

        assert upstream_control.reconnect_requested is True
        assert upstream_control.suppress_downstream_event is True
        assert pending_request.previous_response_id is None
        assert "previous_response_id" not in json.loads(pending_request.request_text or "{}")
        assert pending_request.excluded_account_ids == {account.id}
        assert pending_request.replay_count == 1
        failover = current_admission_failover()
        assert failover is not None
        assert failover.from_account_id == account.id

        pending.append(pending_request)
        upstream_control = proxy_service._WebSocketUpstreamControl()
        pending_request.response_create_gate_acquired = True
        await _drive(
            service,
            account,
            pending,
            {"type": "response.created", "response": {"id": "resp_y", "status": "in_progress"}},
            upstream_control,
        )
        completed = await _drive(
            service,
            account,
            pending,
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_y",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "OK"}],
                        }
                    ],
                },
            },
            upstream_control,
        )
        assert json.loads(completed)["response"]["id"] == "resp_x"
        assert await service.drain_persistence_tasks(timeout_seconds=2)
        assert request_logs.calls
        assert request_logs.calls[-1]["admission_failover_retried"] is True
        assert request_logs.calls[-1]["admission_failover_from_account_id"] == account.id
    finally:
        reset_admission_request_context()
        history_module.set_conversation_history_cache(None)
        cache.close()


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_accepted_history_failover_does_not_run_a_second_time(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _cache(tmp_path)
    from app.modules.proxy import conversation_history as history_module

    history_module.set_conversation_history_cache(cache)
    _seed_history(cache)
    reset_history_replay_context()
    reset_admission_request_context()
    _patch_jitter(monkeypatch)
    service = proxy_service.ProxyService(_repo_factory(_RequestLogsRecorder()))
    finalize = AsyncMock()
    monkeypatch.setattr(service, "_finalize_websocket_request_state", finalize)
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _accept(service, account, pending, upstream_control)
        await _drive(service, account, pending, _failure_payload("server_error"), upstream_control)
        assert pending_request.replay_count == 1
        assert pending_request.previous_response_id is None
        pending.append(pending_request)
        upstream_control = proxy_service._WebSocketUpstreamControl()
        pending_request.response_create_gate_acquired = True
        await _drive(
            service,
            account,
            pending,
            {"type": "response.created", "response": {"id": "resp_y", "status": "in_progress"}},
            upstream_control,
        )
        upstream_control = proxy_service._WebSocketUpstreamControl()
        text = await _drive(service, account, pending, _failure_payload("server_is_overloaded"), upstream_control)
        assert "server_is_overloaded" in text
        assert upstream_control.reconnect_requested is False
        assert pending_request.replay_count == 1
        assert pending_request.excluded_account_ids == {account.id}
        finalize.assert_awaited()
    finally:
        reset_admission_request_context()
        history_module.set_conversation_history_cache(None)
        cache.close()


@pytest.mark.asyncio
async def test_accepted_admission_cache_miss_surfaces_without_failover(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _cache(tmp_path)
    from app.modules.proxy import conversation_history as history_module

    history_module.set_conversation_history_cache(cache)
    reset_history_replay_context()
    reset_admission_request_context()
    _patch_jitter(monkeypatch)
    service = proxy_service.ProxyService(_repo_factory(_RequestLogsRecorder()))
    finalize = AsyncMock()
    monkeypatch.setattr(service, "_finalize_websocket_request_state", finalize)
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _accept(service, account, pending, upstream_control)
        text = await _drive(service, account, pending, _failure_payload("server_error"), upstream_control)
        assert json.loads(text)["error"]["code"] == "server_error"
        assert upstream_control.reconnect_requested is False
        assert pending_request.excluded_account_ids == set()
        assert pending_request.previous_response_id == "resp-1"
        assert current_admission_failover() is None
        finalize.assert_awaited()
    finally:
        reset_admission_request_context()
        history_module.set_conversation_history_cache(None)
        cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output_event",
    [
        {
            "type": "response.output_item.added",
            "response_id": "resp_x",
            "output_index": 0,
            "item": {"id": "fc_1", "type": "function_call", "name": "lookup", "arguments": ""},
        },
        {
            "type": "response.function_call_arguments.delta",
            "response_id": "resp_x",
            "delta": '{"q":',
        },
        {
            "type": "response.output_text.delta",
            "response_id": "resp_x",
            "delta": "hello",
        },
        {
            "type": "response.reasoning_text.delta",
            "response_id": "resp_x",
            "delta": "thinking",
        },
    ],
)
async def test_accepted_admission_failure_after_any_output_does_not_fail_over(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    output_event: dict[str, JsonValue],
) -> None:
    cache = _cache(tmp_path)
    from app.modules.proxy import conversation_history as history_module

    history_module.set_conversation_history_cache(cache)
    _seed_history(cache)
    reset_history_replay_context()
    reset_admission_request_context()
    _patch_jitter(monkeypatch)
    service = proxy_service.ProxyService(_repo_factory(_RequestLogsRecorder()))
    finalize = AsyncMock()
    monkeypatch.setattr(service, "_finalize_websocket_request_state", finalize)
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())
    account = _account("acct-a")
    pending_request = _accepted_anchor_state(preferred_account_id=None, replay_required_account_id=None)
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _accept(service, account, pending, upstream_control)
        await _drive(service, account, pending, output_event, upstream_control)
        assert pending_request.upstream_model_output_seen is True
        upstream_control = proxy_service._WebSocketUpstreamControl()
        text = await _drive(service, account, pending, _failure_payload("server_error"), upstream_control)
        assert "server_error" in text
        assert upstream_control.reconnect_requested is False
        assert pending_request.excluded_account_ids == set()
        assert current_admission_failover() is None
        finalize.assert_awaited()
    finally:
        reset_admission_request_context()
        history_module.set_conversation_history_cache(None)
        cache.close()


class _OrderUpstream:
    def __init__(self, messages: list[SimpleNamespace], order: list[str], *, record_close: bool) -> None:
        self.sent_text: list[str] = []
        self._messages: asyncio.Queue[SimpleNamespace] = asyncio.Queue()
        self._order = order
        self._record_close = record_close
        for message in messages:
            self._messages.put_nowait(message)

    async def send_text(self, text: str) -> None:
        self.sent_text.append(text)

    async def send_bytes(self, _data: bytes) -> None:
        return None

    async def receive(self) -> SimpleNamespace:
        return await self._messages.get()

    async def close(self) -> None:
        if self._record_close:
            self._order.append("close")


class _OrderDownstream:
    def __init__(self, request_text: str) -> None:
        self._request_text = request_text
        self._request_sent = False
        self._disconnect_sent = False
        self._done = asyncio.Event()
        self.sent_text: list[str] = []

    async def receive(self) -> dict[str, object]:
        if not self._request_sent:
            self._request_sent = True
            return {"type": "websocket.receive", "text": self._request_text}
        if not self._disconnect_sent:
            await self._done.wait()
            self._disconnect_sent = True
            return {"type": "websocket.disconnect"}
        return {"type": "websocket.disconnect"}

    async def send_text(self, text: str) -> None:
        self.sent_text.append(text)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}
        if payload.get("type") in {"response.completed", "response.failed", "error"}:
            self._done.set()

    async def send_bytes(self, _data: bytes) -> None:
        return None

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        del code, reason
        self._done.set()


def _ws_text(payload: dict[str, JsonValue]) -> SimpleNamespace:
    text = json.dumps(payload, separators=(",", ":"))
    return SimpleNamespace(kind="text", text=text, data=None, close_code=None, error=None)


@pytest.mark.asyncio
async def test_accepted_admission_failover_closes_the_original_upstream_before_switch(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import shutdown as shutdown_state
    from app.modules.proxy import conversation_history as history_module

    cache = _cache(tmp_path)
    history_module.set_conversation_history_cache(cache)
    _seed_history(cache)
    reset_history_replay_context()
    reset_admission_request_context()
    shutdown_state.reset()
    _patch_jitter(monkeypatch)
    service = proxy_service.ProxyService(_repo_factory(_RequestLogsRecorder()))
    settings = SimpleNamespace(
        prefer_earlier_reset_accounts=False,
        prefer_earlier_reset_window="secondary",
        sticky_threads_enabled=False,
        sticky_reallocation_budget_threshold_pct=95.0,
        upstream_stream_transport="default",
        openai_cache_affinity_max_age_seconds=300,
        openai_prompt_cache_key_derivation_enabled=True,
        routing_strategy="usage_weighted",
        proxy_request_budget_seconds=75.0,
        compact_request_budget_seconds=75.0,
        transcription_request_budget_seconds=120.0,
        upstream_compact_timeout_seconds=None,
        http_responses_session_bridge_gateway_safe_mode=False,
        trace_channels=frozenset(),
        proxy_token_refresh_limit=32,
        proxy_upstream_websocket_connect_limit=64,
        proxy_account_response_create_limit=4,
        proxy_account_stream_limit=8,
        proxy_account_stream_recovery_reserve=1,
        proxy_api_key_fair_share_congestion_threshold_pct=0,
        proxy_response_create_limit=64,
        proxy_compact_response_create_limit=16,
        proxy_admission_wait_timeout_seconds=10.0,
        max_sse_event_bytes=16 * 1024 * 1024,
        http_responses_session_bridge_instance_id="test-instance",
        http_responses_session_bridge_instance_ring=[],
        http_downstream_transport_policy="smart",
        stream_idle_timeout_seconds=300.0,
        proxy_downstream_websocket_idle_timeout_seconds=120.0,
        sse_keepalive_interval_seconds=0.0,
    )

    async def settings_get() -> SimpleNamespace:
        return settings

    monkeypatch.setattr(proxy_service, "get_settings_cache", lambda: SimpleNamespace(get=settings_get))
    monkeypatch.setattr(proxy_service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())
    monkeypatch.setattr(service, "_resolve_websocket_previous_response_owner", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_resolve_compact_turn_state_owner", AsyncMock(return_value=None))
    order: list[str] = []
    original = _OrderUpstream(
        [
            _ws_text({"type": "response.created", "response": {"id": "resp_x", "status": "in_progress"}}),
            _ws_text({"type": "response.in_progress", "response": {"id": "resp_x", "status": "in_progress"}}),
            _ws_text(_failure_payload("server_error")),
        ],
        order,
        record_close=True,
    )
    replacement = _OrderUpstream(
        [
            _ws_text({"type": "response.created", "response": {"id": "resp_y", "status": "in_progress"}}),
            _ws_text(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_y",
                        "status": "completed",
                        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                    },
                }
            ),
        ],
        order,
        record_close=False,
    )
    connect_calls = 0

    async def connect_proxy_websocket(self, headers, **kwargs):
        del self, headers, kwargs
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls == 1:
            return _account("acct-a"), original
        order.append("switch")
        return _account("acct-b"), replacement

    monkeypatch.setattr(proxy_service.ProxyService, "_connect_proxy_websocket", connect_proxy_websocket)
    downstream = _OrderDownstream(
        json.dumps(
            {
                "type": "response.create",
                "model": "gpt-6-astra",
                "instructions": "",
                "previous_response_id": "resp-1",
                "input": [
                    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "more"}]},
                ],
            },
            separators=(",", ":"),
        )
    )
    try:
        await asyncio.wait_for(
            service.proxy_responses_websocket(
                cast(Any, downstream),
                {},
                codex_session_affinity=False,
                openai_cache_affinity=False,
                api_key=None,
            ),
            timeout=5,
        )
        assert connect_calls == 2
        assert order.index("close") < order.index("switch")
        assert replacement.sent_text
        assert "previous_response_id" not in json.loads(replacement.sent_text[0])
    finally:
        shutdown_state.reset()
        reset_admission_request_context()
        history_module.set_conversation_history_cache(None)
        cache.close()


def _anchor_loss_payload(response_id: str | None = None) -> dict[str, JsonValue]:
    error: dict[str, JsonValue] = {
        "type": "invalid_request_error",
        "code": "previous_response_not_found",
        "message": "Previous response with id 'resp-1' not found.",
        "param": "previous_response_id",
    }
    if response_id is None:
        return {"type": "error", "status": 400, "error": error}
    return {"type": "response.failed", "response": {"id": response_id, "status": "failed", "error": error}}


def _anchor_loss_service(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    seeded: bool,
) -> tuple[ConversationHistoryCache, Any, _RequestLogsRecorder, AsyncMock]:
    from app.modules.proxy import conversation_history as history_module

    cache = _cache(tmp_path)
    history_module.set_conversation_history_cache(cache)
    if seeded:
        _seed_history(cache)
    reset_history_replay_context()
    reset_admission_request_context()
    _clear_websocket_stale_previous_response_cache()
    _patch_jitter(monkeypatch)
    request_logs = _RequestLogsRecorder()
    service = proxy_service.ProxyService(_repo_factory(request_logs))
    handle_stream_error = AsyncMock()
    monkeypatch.setattr(service, "_handle_stream_error", handle_stream_error)
    return cache, service, request_logs, handle_stream_error


def _close_anchor_loss_service(cache: ConversationHistoryCache) -> None:
    from app.modules.proxy import conversation_history as history_module

    reset_admission_request_context()
    _clear_websocket_stale_previous_response_cache()
    history_module.set_conversation_history_cache(None)
    cache.close()


def _anchor_fail_closed_logged(caplog: pytest.LogCaptureFixture) -> bool:
    return any(
        "continuity_fail_closed" in record.getMessage() and "reason=previous_response_not_found" in record.getMessage()
        for record in caplog.records
    )


def _anchor_marked_stale() -> bool:
    return _is_websocket_stale_previous_response(previous_response_id="resp-1", api_key_id=None)


def _assert_fail_closed_terminal(text: str) -> None:
    event = json.loads(text)
    assert event["type"] == "response.failed"
    assert event["response"]["error"]["code"] == "stream_incomplete"
    assert "resp-1" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_response_id", [None, "resp_x"], ids=["error-event", "response-failed"])
async def test_websocket_anchor_loss_after_created_replays_cached_history_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    terminal_response_id: str | None,
) -> None:
    cache, service, request_logs, handle_stream_error = _anchor_loss_service(tmp_path, monkeypatch, seeded=True)
    caplog.set_level(logging.INFO)
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _accept(service, account, pending, upstream_control)
        await _drive(service, account, pending, _anchor_loss_payload(terminal_response_id), upstream_control)

        assert upstream_control.reconnect_requested is True
        assert upstream_control.suppress_downstream_event is True
        assert upstream_control.replay_request_state is pending_request
        replay_body = json.loads(pending_request.request_text or "{}")
        assert "previous_response_id" not in replay_body
        assert "kept" in json.dumps(replay_body["input"])
        assert "more" in json.dumps(replay_body["input"])
        assert pending_request.replay_count == 1
        assert pending_request.replay_downstream_response_id == "resp_x"
        assert pending_request.excluded_account_ids == set()
        handle_stream_error.assert_not_awaited()
        assert not _anchor_fail_closed_logged(caplog)
        assert not _anchor_marked_stale()

        pending.append(pending_request)
        pending_request.response_create_gate_acquired = True
        upstream_control = proxy_service._WebSocketUpstreamControl()
        await _drive(
            service,
            account,
            pending,
            {"type": "response.created", "response": {"id": "resp_y", "status": "in_progress"}},
            upstream_control,
        )
        assert upstream_control.suppress_downstream_event is True
        upstream_control = proxy_service._WebSocketUpstreamControl()
        completed = await _drive(
            service,
            account,
            pending,
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_y",
                    "status": "completed",
                    "output": [
                        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "OK"}]}
                    ],
                },
            },
            upstream_control,
        )
        assert json.loads(completed)["response"]["id"] == "resp_x"
        assert await service.drain_persistence_tasks(timeout_seconds=2)
        assert request_logs.calls[-1]["history_replay_reason"] == "previous_response_not_found"
    finally:
        _close_anchor_loss_service(cache)


@pytest.mark.asyncio
async def test_websocket_anchor_loss_before_created_replays_without_fail_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache, service, _request_logs, handle_stream_error = _anchor_loss_service(tmp_path, monkeypatch, seeded=True)
    caplog.set_level(logging.INFO)
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _drive(service, account, pending, _anchor_loss_payload(), upstream_control)

        assert upstream_control.reconnect_requested is True
        assert upstream_control.suppress_downstream_event is True
        assert upstream_control.replay_request_state is pending_request
        assert pending_request.previous_response_id is None
        assert "previous_response_id" not in json.loads(pending_request.request_text or "{}")
        assert pending_request.replay_count == 1
        assert pending_request.replay_downstream_response_id is None
        handle_stream_error.assert_not_awaited()
        assert not _anchor_fail_closed_logged(caplog)
        assert not _anchor_marked_stale()
    finally:
        _close_anchor_loss_service(cache)


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [False, True], ids=["pre-created", "accepted"])
async def test_websocket_anchor_loss_cache_miss_fails_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    accepted: bool,
) -> None:
    cache, service, _request_logs, _handle_stream_error = _anchor_loss_service(tmp_path, monkeypatch, seeded=False)
    caplog.set_level(logging.INFO)
    finalize = AsyncMock()
    monkeypatch.setattr(service, "_finalize_websocket_request_state", finalize)
    account = _account("acct-a")
    pending_request = _accepted_anchor_state(preferred_account_id=None, replay_required_account_id=None)
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        if accepted:
            await _accept(service, account, pending, upstream_control)
        text = await _drive(
            service,
            account,
            pending,
            _anchor_loss_payload("resp_x" if accepted else None),
            upstream_control,
        )

        _assert_fail_closed_terminal(text)
        assert upstream_control.replay_request_state is None
        assert pending_request.previous_response_id == "resp-1"
        assert pending_request.history_replay_used is False
        assert pending_request.replay_count == 0
        assert _anchor_fail_closed_logged(caplog)
        assert "fresh_replay_available=false" in caplog.text
        assert _anchor_marked_stale()
        finalize.assert_awaited()
    finally:
        _close_anchor_loss_service(cache)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output_event",
    [
        {
            "type": "response.output_item.added",
            "response_id": "resp_x",
            "output_index": 0,
            "item": {"id": "fc_1", "type": "function_call", "name": "lookup", "arguments": ""},
        },
        {"type": "response.output_text.delta", "response_id": "resp_x", "delta": "hello"},
        {"type": "response.reasoning_text.delta", "response_id": "resp_x", "delta": "thinking"},
    ],
    ids=["tool-call", "text", "reasoning"],
)
async def test_websocket_anchor_loss_after_model_output_is_not_replayed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    output_event: dict[str, JsonValue],
) -> None:
    cache, service, _request_logs, _handle_stream_error = _anchor_loss_service(tmp_path, monkeypatch, seeded=True)
    finalize = AsyncMock()
    monkeypatch.setattr(service, "_finalize_websocket_request_state", finalize)
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _accept(service, account, pending, upstream_control)
        await _drive(service, account, pending, output_event, upstream_control)
        upstream_control = proxy_service._WebSocketUpstreamControl()
        text = await _drive(service, account, pending, _anchor_loss_payload("resp_x"), upstream_control)

        _assert_fail_closed_terminal(text)
        assert upstream_control.replay_request_state is None
        assert pending_request.previous_response_id == "resp-1"
        assert pending_request.history_replay_used is False
        finalize.assert_awaited()
    finally:
        _close_anchor_loss_service(cache)


@pytest.mark.asyncio
@pytest.mark.parametrize("spent_by", ["earlier_retry", "first_replay"])
async def test_websocket_anchor_loss_replays_at_most_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    spent_by: str,
) -> None:
    cache, service, _request_logs, _handle_stream_error = _anchor_loss_service(tmp_path, monkeypatch, seeded=True)
    finalize = AsyncMock()
    monkeypatch.setattr(service, "_finalize_websocket_request_state", finalize)
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        if spent_by == "earlier_retry":
            mark_transparent_retry(pending_request.request_id)
        else:
            await _drive(service, account, pending, _anchor_loss_payload(), upstream_control)
            assert upstream_control.replay_request_state is pending_request
            pending.append(pending_request)
            upstream_control = proxy_service._WebSocketUpstreamControl()
        text = await _drive(service, account, pending, _anchor_loss_payload(), upstream_control)

        _assert_fail_closed_terminal(text)
        assert upstream_control.replay_request_state is None
        assert pending_request.replay_count == (1 if spent_by == "first_replay" else 0)
    finally:
        _close_anchor_loss_service(cache)


def _sequenced(payload: dict[str, JsonValue], sequence_number: int) -> dict[str, JsonValue]:
    return {**payload, "sequence_number": sequence_number}


_RESPONSE_CREATED_X: dict[str, JsonValue] = {
    "type": "response.created",
    "response": {"id": "resp_x", "status": "in_progress"},
}
_RESPONSE_IN_PROGRESS_X: dict[str, JsonValue] = {
    "type": "response.in_progress",
    "response": {"id": "resp_x", "status": "in_progress"},
}
_RESPONSE_CREATED_Y: dict[str, JsonValue] = {
    "type": "response.created",
    "response": {"id": "resp_y", "status": "in_progress"},
}
_RESPONSE_IN_PROGRESS_Y: dict[str, JsonValue] = {
    "type": "response.in_progress",
    "response": {"id": "resp_y", "status": "in_progress"},
}


@pytest.mark.asyncio
async def test_websocket_anchor_loss_replay_suppresses_the_sequenced_prelude(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, service, _request_logs, _handle_stream_error = _anchor_loss_service(tmp_path, monkeypatch, seeded=True)
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _drive(service, account, pending, _sequenced(_RESPONSE_CREATED_X, 0), upstream_control)
        await _drive(service, account, pending, _sequenced(_RESPONSE_IN_PROGRESS_X, 1), upstream_control)
        pending_request.last_downstream_sequence_number = 1
        upstream_control = proxy_service._WebSocketUpstreamControl()
        await _drive(service, account, pending, _sequenced(_anchor_loss_payload("resp_x"), 2), upstream_control)
        assert upstream_control.replay_request_state is pending_request

        pending.append(pending_request)
        pending_request.response_create_gate_acquired = True
        for prelude in (_sequenced(_RESPONSE_CREATED_Y, 0), _sequenced(_RESPONSE_IN_PROGRESS_Y, 1)):
            upstream_control = proxy_service._WebSocketUpstreamControl()
            await _drive(service, account, pending, prelude, upstream_control)
            assert upstream_control.suppress_downstream_event is True
        upstream_control = proxy_service._WebSocketUpstreamControl()
        completed = await _drive(
            service,
            account,
            pending,
            _sequenced({"type": "response.completed", "response": {"id": "resp_y", "status": "completed"}}, 2),
            upstream_control,
        )
        assert upstream_control.suppress_downstream_event is False
        assert json.loads(completed)["response"]["id"] == "resp_x"
    finally:
        _close_anchor_loss_service(cache)


@pytest.mark.asyncio
async def test_websocket_anchor_loss_replay_sequence_must_advance(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, service, _request_logs, _handle_stream_error = _anchor_loss_service(tmp_path, monkeypatch, seeded=True)
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _drive(service, account, pending, _sequenced(_RESPONSE_CREATED_X, 0), upstream_control)
        pending_request.last_downstream_sequence_number = 0
        await _drive(service, account, pending, _sequenced(_anchor_loss_payload("resp_x"), 1), upstream_control)
        assert upstream_control.replay_request_state is pending_request
        assert pending_request.suppress_next_in_progress_downstream is False

        pending.append(pending_request)
        pending_request.response_create_gate_acquired = True
        upstream_control = proxy_service._WebSocketUpstreamControl()
        await _drive(service, account, pending, _sequenced(_RESPONSE_CREATED_Y, 0), upstream_control)
        with pytest.raises(_WebSocketReplaySequenceRegression):
            await _drive(service, account, pending, _sequenced(_RESPONSE_IN_PROGRESS_Y, 0), upstream_control)
    finally:
        _close_anchor_loss_service(cache)


@pytest.mark.asyncio
async def test_websocket_anchor_loss_beyond_the_prelude_watermark_fails_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, service, _request_logs, _handle_stream_error = _anchor_loss_service(tmp_path, monkeypatch, seeded=True)
    finalize = AsyncMock()
    monkeypatch.setattr(service, "_finalize_websocket_request_state", finalize)
    account = _account("acct-a")
    pending_request = _accepted_anchor_state()
    pending: deque[_WebSocketRequestState] = deque([pending_request])
    upstream_control = proxy_service._WebSocketUpstreamControl()
    try:
        await _drive(service, account, pending, _sequenced(_RESPONSE_CREATED_X, 0), upstream_control)
        await _drive(service, account, pending, _sequenced(_RESPONSE_IN_PROGRESS_X, 1), upstream_control)
        pending_request.last_downstream_sequence_number = 2
        upstream_control = proxy_service._WebSocketUpstreamControl()
        text = await _drive(service, account, pending, _sequenced(_anchor_loss_payload("resp_x"), 3), upstream_control)

        _assert_fail_closed_terminal(text)
        assert upstream_control.replay_request_state is None
        assert pending_request.history_replay_used is False
        finalize.assert_awaited()
    finally:
        _close_anchor_loss_service(cache)
