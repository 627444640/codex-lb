"""Soft-preferred admission failover on selection and the HTTP bridge."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from collections.abc import Iterator
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import anyio
import pytest

import app.modules.proxy.load_balancer as load_balancer_module
from app.core.clients.proxy import ProxyResponseError
from app.core.clients.proxy_websocket import UpstreamWebSocket
from app.core.config.settings import Settings
from app.db.models import Account, AccountStatus, StickySessionKind
from app.modules.proxy import service as proxy_service
from app.modules.proxy._load_balancer.admission_breaker import current_admission_failover
from app.modules.proxy._load_balancer.types import RuntimeState
from app.modules.proxy.account_cache import AccountSelectionCache
from app.modules.proxy.conversation_history import (
    ConversationHistoryCache,
    current_history_replay,
    reset_history_replay_context,
    set_conversation_history_cache,
)
from app.modules.proxy.load_balancer import AccountSelection, LoadBalancer
from tests.unit.test_load_balancer_contract import _account, _balancer

pytestmark = pytest.mark.unit

_SICK = "acc-sick"
_HEALTHY = "acc-healthy"


class _StopAfterCapture(Exception):
    """Halt the bridge once the upstream body has been captured."""


class _SettingsCache:
    def __init__(self, settings: SimpleNamespace) -> None:
        self._settings = settings

    async def get(self) -> SimpleNamespace:
        return self._settings


@pytest.fixture(autouse=True)
def _reset_retry_marks() -> Iterator[None]:
    reset_history_replay_context()
    yield
    reset_history_replay_context()


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
    try:
        yield cache
    finally:
        set_conversation_history_cache(None)


def _runtime_settings(*, breaker_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        circuit_breaker_enabled=False,
        account_admission_breaker_enabled=breaker_enabled,
        account_admission_breaker_failure_threshold=3,
        account_admission_breaker_window_seconds=60.0,
        account_admission_breaker_open_seconds=300.0,
        proxy_account_response_create_limit=4,
        proxy_account_stream_limit=8,
        proxy_account_caps_scope="replica",
        proxy_account_stream_recovery_reserve=0,
        proxy_api_key_fair_share_congestion_threshold_pct=0,
        routing_strategy="usage_weighted",
        sticky_reallocation_budget_threshold_pct=95.0,
        http_responses_session_bridge_enabled=True,
        http_responses_session_bridge_prompt_cache_idle_ttl_seconds=3600,
        http_responses_session_bridge_gateway_safe_mode=False,
        sticky_threads_enabled=False,
        openai_cache_affinity_max_age_seconds=1800,
    )


def _block_account(balancer: LoadBalancer, account_id: str, *, probe_in_flight: bool = False) -> None:
    now = time.time()
    if probe_in_flight:
        balancer._runtime[account_id] = RuntimeState(
            admission_open_until=now - 1,
            admission_probe_in_flight=True,
            admission_probe_started_at=now,
            admission_half_open_logged=True,
        )
        return
    balancer._runtime[account_id] = RuntimeState(admission_open_until=now + 300)


def _install_selection(
    monkeypatch: pytest.MonkeyPatch,
    accounts: list[Account],
    *,
    breaker_enabled: bool,
) -> tuple[proxy_service.ProxyService, LoadBalancer, Any]:
    balancer, _accounts_repo, _usage_repo, sticky = _balancer(accounts, AccountSelectionCache(ttl_seconds=60))
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    service._load_balancer = balancer
    settings = _runtime_settings(breaker_enabled=breaker_enabled)
    monkeypatch.setattr(load_balancer_module, "get_settings", lambda: settings)
    monkeypatch.setattr(load_balancer_module, "set_normal", lambda: None)
    monkeypatch.setattr(load_balancer_module, "set_degraded", lambda _reason: None)
    monkeypatch.setattr("app.modules.proxy._load_balancer.admission_breaker.get_settings", lambda: settings)
    monkeypatch.setattr(proxy_service, "get_settings", lambda: settings)
    monkeypatch.setattr(proxy_service, "get_settings_cache", lambda: _SettingsCache(settings))
    return service, balancer, sticky


async def _select_preferred(
    service: proxy_service.ProxyService,
    preferred: str,
    *,
    fallback: bool = True,
    request_id: str = "req-soft-preferred",
) -> AccountSelection:
    return await service._select_account_with_budget(
        time.monotonic() + 30,
        request_id=request_id,
        kind="http_bridge",
        request_stage="first_turn",
        preferred_account_id=preferred,
        fallback_on_preferred_account_unavailable=fallback,
        routing_strategy="usage_weighted",
    )


def _seed_history(cache: ConversationHistoryCache, *, file_id: str | None = None) -> None:
    content: list[dict[str, str]] = [{"type": "input_text", "text": "kept"}]
    if file_id is not None:
        content.append({"type": "input_file", "file_id": file_id})
    cache.record_completed_turn(
        request_body={
            "model": "gpt-5.4",
            "input": [{"type": "message", "role": "user", "content": content}],
        },
        response_id="resp-1",
        output_items=[{"type": "message", "text": "ok"}],
    )


def _follow_up_payload() -> proxy_service.ResponsesRequest:
    return proxy_service.ResponsesRequest.model_validate(
        {
            "model": "gpt-5.4",
            "instructions": "",
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "more"}]}],
            "previous_response_id": "resp-1",
        }
    )


def _bridge_session() -> proxy_service._HTTPBridgeSession:
    return proxy_service._HTTPBridgeSession(
        key=proxy_service._HTTPBridgeSessionKey("request", "soft-turn", None, strength="soft"),
        headers={},
        affinity=proxy_service._AffinityPolicy(key="soft-turn"),
        request_model="gpt-5.4",
        account=cast(
            Any,
            SimpleNamespace(
                id=_HEALTHY,
                chatgpt_account_id="workspace-healthy",
                status=AccountStatus.ACTIVE,
                plan_type="plus",
            ),
        ),
        upstream=cast(UpstreamWebSocket, SimpleNamespace(close=AsyncMock())),
        upstream_control=proxy_service._WebSocketUpstreamControl(),
        pending_requests=deque(),
        pending_lock=anyio.Lock(),
        response_create_gate=asyncio.Semaphore(1),
        queued_request_count=0,
        last_used_at=1.0,
        idle_ttl_seconds=120.0,
    )


def _patch_bridge(
    monkeypatch: pytest.MonkeyPatch,
    service: proxy_service.ProxyService,
    *,
    breaker_enabled: bool,
) -> tuple[AsyncMock, dict[str, Any]]:
    settings = _runtime_settings(breaker_enabled=breaker_enabled)
    app_settings = Settings(http_responses_session_bridge_enabled=True)
    monkeypatch.setattr(proxy_service, "get_settings", lambda: app_settings)
    monkeypatch.setattr(proxy_service, "get_settings_cache", lambda: _SettingsCache(settings))
    monkeypatch.setattr("app.modules.proxy._load_balancer.admission_breaker.get_settings", lambda: settings)
    monkeypatch.setattr(service._durable_bridge, "lookup_request_targets", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_resolve_file_account_for_responses", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_http_bridge_local_owner_account_id", AsyncMock(return_value=_SICK))
    monkeypatch.setattr(service, "_resolve_websocket_previous_response_owner", AsyncMock(return_value=_SICK))

    def fake_prepare(
        payload: proxy_service.ResponsesRequest,
        headers: Any,
        *,
        api_key: Any,
        api_key_reservation: Any,
        request_id: str,
        client_ip: str | None = None,
        preserve_responses_lite_client_metadata: bool = False,
    ) -> tuple[proxy_service._WebSocketRequestState, str]:
        del api_key, client_ip, preserve_responses_lite_client_metadata
        body = payload.model_dump(mode="json")
        body["type"] = "response.create"
        text = json.dumps(body, separators=(",", ":"))
        turn_state = None
        if isinstance(headers, dict):
            turn_state = headers.get("x-codex-turn-state")
        state = proxy_service._WebSocketRequestState(
            request_id=request_id,
            model=payload.model,
            service_tier=None,
            reasoning_effort=None,
            api_key_reservation=api_key_reservation,
            started_at=time.monotonic(),
            transport="http",
            previous_response_id=payload.previous_response_id,
            hard_continuity_anchor=payload.previous_response_id is not None or bool(turn_state),
            request_text=text,
            awaiting_response_created=True,
        )
        return state, text

    monkeypatch.setattr(service, "_prepare_http_bridge_request", fake_prepare)
    get_or_create = AsyncMock(return_value=_bridge_session())
    monkeypatch.setattr(service, "_get_or_create_http_bridge_session", get_or_create)
    captured: dict[str, Any] = {}

    async def capture_events(
        _session: proxy_service._HTTPBridgeSession,
        *,
        request_state: proxy_service._WebSocketRequestState,
        text_data: str,
        queue_limit: int,
        propagate_http_errors: bool,
        downstream_turn_state: str | None,
        request_deadline: float | None = None,
    ):
        del queue_limit, propagate_http_errors, downstream_turn_state, request_deadline
        captured["text"] = text_data
        captured["request_state"] = request_state
        raise _StopAfterCapture
        yield ""  # pragma: no cover

    monkeypatch.setattr(service, "_stream_http_bridge_session_events", capture_events)
    return get_or_create, captured


async def _drive_bridge(
    service: proxy_service.ProxyService,
    *,
    headers: dict[str, str] | None = None,
) -> None:
    async for _line in service._stream_via_http_bridge(
        _follow_up_payload(),
        headers=headers or {},
        codex_session_affinity=False,
        propagate_http_errors=True,
        openai_cache_affinity=False,
        api_key=None,
        api_key_reservation=None,
        suppress_text_done_events=False,
        idle_ttl_seconds=120.0,
        codex_idle_ttl_seconds=900.0,
        max_sessions=8,
        queue_limit=4,
    ):
        pass


@pytest.mark.asyncio
async def test_soft_preferred_open_breaker_selects_other_account(monkeypatch: pytest.MonkeyPatch) -> None:
    service, balancer, _sticky = _install_selection(
        monkeypatch,
        [_account(_SICK), _account(_HEALTHY)],
        breaker_enabled=True,
    )
    _block_account(balancer, _SICK)

    selection = await _select_preferred(service, _SICK)

    assert selection.account is not None
    assert selection.account.id == _HEALTHY
    assert selection.error_code is None
    failover = current_admission_failover()
    assert failover is not None
    assert failover.from_account_id == _SICK


@pytest.mark.asyncio
async def test_soft_preferred_half_open_probe_taken_selects_other_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, balancer, _sticky = _install_selection(
        monkeypatch,
        [_account(_SICK), _account(_HEALTHY)],
        breaker_enabled=True,
    )
    _block_account(balancer, _SICK, probe_in_flight=True)

    selection = await _select_preferred(service, _SICK, request_id="req-half-open-probe")

    assert selection.account is not None
    assert selection.account.id == _HEALTHY


@pytest.mark.asyncio
async def test_half_open_free_probe_keeps_soft_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    service, balancer, _sticky = _install_selection(
        monkeypatch,
        [_account(_SICK), _account(_HEALTHY)],
        breaker_enabled=True,
    )
    balancer._runtime[_SICK] = RuntimeState(
        admission_open_until=time.time() - 1,
        admission_probe_in_flight=False,
        admission_half_open_logged=True,
    )

    selection = await _select_preferred(service, _SICK, request_id="req-half-open-free")

    assert selection.account is not None
    assert selection.account.id == _SICK
    assert current_admission_failover() is None


@pytest.mark.asyncio
async def test_soft_preferred_open_breaker_without_sibling_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, balancer, _sticky = _install_selection(
        monkeypatch,
        [_account(_SICK)],
        breaker_enabled=True,
    )
    _block_account(balancer, _SICK)

    selection = await _select_preferred(service, _SICK, request_id="req-no-sibling")

    assert selection.account is None
    assert selection.error_code == "account_admission_breaker_open"
    assert selection.error_message == "No available accounts"


@pytest.mark.asyncio
async def test_ownership_pin_open_breaker_stays_on_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    service, balancer, _sticky = _install_selection(
        monkeypatch,
        [_account(_SICK), _account(_HEALTHY)],
        breaker_enabled=True,
    )
    _block_account(balancer, _SICK)

    selection = await _select_preferred(service, _SICK, fallback=False, request_id="req-ownership-pin")

    assert selection.account is not None
    assert selection.account.id == _SICK
    assert current_admission_failover() is None


@pytest.mark.asyncio
async def test_hard_codex_owner_open_breaker_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _service, balancer, sticky = _install_selection(
        monkeypatch,
        [_account(_SICK), _account(_HEALTHY)],
        breaker_enabled=True,
    )
    sticky.account_id = _SICK
    _block_account(balancer, _SICK)

    selection = await balancer.select_account(
        "codex-hard-owner",
        sticky_kind=StickySessionKind.CODEX_SESSION,
        sticky_source="turn_state",
        routing_strategy="usage_weighted",
    )

    assert selection.account is None
    assert selection.error_code == "account_admission_breaker_open"
    assert current_admission_failover() is None


@pytest.mark.asyncio
async def test_disabled_breaker_keeps_soft_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    service, balancer, _sticky = _install_selection(
        monkeypatch,
        [_account(_SICK), _account(_HEALTHY)],
        breaker_enabled=False,
    )
    _block_account(balancer, _SICK)

    selection = await _select_preferred(service, _SICK, request_id="req-breaker-disabled")

    assert selection.account is not None
    assert selection.account.id == _SICK
    assert current_admission_failover() is None


@pytest.mark.asyncio
async def test_follow_up_with_cache_replays_on_fallback_account(
    monkeypatch: pytest.MonkeyPatch,
    history_cache: ConversationHistoryCache,
) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    _block_account(service._load_balancer, _SICK)
    _seed_history(history_cache)
    get_or_create, captured = _patch_bridge(monkeypatch, service, breaker_enabled=True)

    with pytest.raises(_StopAfterCapture):
        await _drive_bridge(service)

    assert get_or_create.await_count == 1
    created = get_or_create.await_args
    assert created is not None
    assert created.kwargs["previous_response_id"] is None
    assert created.kwargs["preferred_account_id"] is None
    assert _SICK in set(created.kwargs["exclude_account_ids"] or ())
    body = json.loads(captured["text"])
    assert "previous_response_id" not in body
    rendered_input = json.dumps(body["input"])
    assert "kept" in rendered_input
    assert "more" in rendered_input
    replay = current_history_replay()
    assert replay is not None
    assert replay.reason == "owner_unavailable"
    request_state = captured["request_state"]
    assert request_state.history_replay_mark is not None
    assert request_state.history_replay_mark.reason == "owner_unavailable"
    failover = current_admission_failover()
    assert failover is not None
    assert failover.from_account_id == _SICK


@pytest.mark.asyncio
async def test_follow_up_without_cache_returns_503_without_forwarding(
    monkeypatch: pytest.MonkeyPatch,
    history_cache: ConversationHistoryCache,
) -> None:
    del history_cache
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    _block_account(service._load_balancer, _SICK)
    get_or_create, captured = _patch_bridge(monkeypatch, service, breaker_enabled=True)

    with pytest.raises(ProxyResponseError) as exc_info:
        await _drive_bridge(service)

    assert exc_info.value.status_code == 503
    assert exc_info.value.payload["error"]["code"] == "account_admission_breaker_open"
    assert exc_info.value.payload["error"]["message"] == "No available accounts"
    assert get_or_create.await_count == 0
    assert "text" not in captured
    assert current_admission_failover() is None
    assert current_history_replay() is None


@pytest.mark.asyncio
async def test_follow_up_with_file_history_is_not_forwarded(
    monkeypatch: pytest.MonkeyPatch,
    history_cache: ConversationHistoryCache,
) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    _block_account(service._load_balancer, _SICK)
    _seed_history(history_cache, file_id="file-kept")
    get_or_create, captured = _patch_bridge(monkeypatch, service, breaker_enabled=True)

    with pytest.raises(ProxyResponseError) as exc_info:
        await _drive_bridge(service)

    assert exc_info.value.status_code == 503
    assert exc_info.value.payload["error"]["code"] == "account_admission_breaker_open"
    assert get_or_create.await_count == 0
    assert "text" not in captured


@pytest.mark.asyncio
async def test_hard_follow_up_keeps_anchor_on_preferred(
    monkeypatch: pytest.MonkeyPatch,
    history_cache: ConversationHistoryCache,
) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    _block_account(service._load_balancer, _SICK)
    _seed_history(history_cache)
    get_or_create, _captured = _patch_bridge(monkeypatch, service, breaker_enabled=True)

    with pytest.raises(_StopAfterCapture):
        await _drive_bridge(service, headers={"x-codex-turn-state": "turn-hard-1"})

    assert get_or_create.await_count == 1
    created = get_or_create.await_args
    assert created is not None
    assert created.kwargs["previous_response_id"] == "resp-1"
    assert created.kwargs["preferred_account_id"] == _SICK
    assert _SICK not in set(created.kwargs["exclude_account_ids"] or ())
    assert current_history_replay() is None
    assert current_admission_failover() is None


@pytest.mark.asyncio
async def test_disabled_breaker_follow_up_keeps_anchor(
    monkeypatch: pytest.MonkeyPatch,
    history_cache: ConversationHistoryCache,
) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    _block_account(service._load_balancer, _SICK)
    _seed_history(history_cache)
    get_or_create, captured = _patch_bridge(monkeypatch, service, breaker_enabled=False)

    with pytest.raises(_StopAfterCapture):
        await _drive_bridge(service)

    assert get_or_create.await_count == 1
    created = get_or_create.await_args
    assert created is not None
    assert created.kwargs["previous_response_id"] == "resp-1"
    assert created.kwargs["preferred_account_id"] == _SICK
    body = json.loads(captured["text"])
    assert body["previous_response_id"] == "resp-1"
    assert current_history_replay() is None
    assert current_admission_failover() is None


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


def _pre_output_upstream_error() -> str:
    return json.dumps(
        {
            "type": "error",
            "error": {
                "type": "server_error",
                "code": "server_error",
                "message": "upstream failed before output",
            },
        },
        separators=(",", ":"),
    )


@pytest.mark.asyncio
async def test_fallback_replay_does_not_switch_again_when_upstream_fails_before_output(
    monkeypatch: pytest.MonkeyPatch,
    history_cache: ConversationHistoryCache,
) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    _block_account(service._load_balancer, _SICK)
    _seed_history(history_cache)
    get_or_create, captured = _patch_bridge(monkeypatch, service, breaker_enabled=True)

    with pytest.raises(_StopAfterCapture):
        await _drive_bridge(service)

    request_state = captured["request_state"]
    request_state.event_queue = asyncio.Queue()
    request_state.skip_request_log = True
    send_text = AsyncMock()
    session = _bridge_session()
    session.upstream = cast(UpstreamWebSocket, SimpleNamespace(send_text=send_text, close=AsyncMock()))
    session.pending_requests = deque([request_state])
    session.queued_request_count = 1
    reconnect = AsyncMock()
    monkeypatch.setattr(service, "_reconnect_http_bridge_session", reconnect)
    monkeypatch.setattr(
        service,
        "_acquire_account_response_create_lease_or_overload",
        AsyncMock(return_value=SimpleNamespace(id="lease-fallback")),
    )
    monkeypatch.setattr(service, "_handle_stream_error", AsyncMock())
    monkeypatch.setattr(service, "_maybe_release_idle_http_bridge_session_lease", AsyncMock())
    monkeypatch.setattr(
        "app.modules.proxy._service.http_bridge.upstream_events.admission_retry_jitter_seconds",
        lambda: 0.0,
    )

    await service._process_http_bridge_upstream_text(session, _pre_output_upstream_error())

    reconnect.assert_not_awaited()
    send_text.assert_not_awaited()
    assert get_or_create.await_count == 1
    assert request_state.replay_count == 0
    assert request_state.history_replay_used is True
    assert request_state.excluded_account_ids == {_SICK}
    failover = current_admission_failover()
    assert failover is not None
    assert failover.from_account_id == _SICK
    replay = current_history_replay()
    assert replay is not None
    assert replay.reason == "owner_unavailable"
    delivered = _queued_payloads(request_state)
    assert delivered
    rendered = json.dumps(delivered)
    assert "server_error" in rendered
    assert "upstream failed before output" in rendered
    assert "response.create" not in rendered
