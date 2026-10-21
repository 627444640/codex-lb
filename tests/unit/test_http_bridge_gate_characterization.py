"""Synthetic admission-boundary evidence; no upstream connection is opened."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.modules.proxy._service.http_bridge import retry_circuit as circuit_module
from app.modules.proxy._service.http_bridge.retry_circuit import (
    _HTTPBridgeRetryCircuitMixin,
    _HTTPBridgeRetryCircuitState,
    _initialize_http_bridge_retry_circuit,
)
from app.modules.proxy._service.support import _HTTPBridgeSession, _HTTPBridgeSessionKey
from app.modules.proxy.durable_bridge_repository import DurableBridgeRetryCircuitSnapshot

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class _CircuitHarness(_HTTPBridgeRetryCircuitMixin):
    def __init__(self) -> None:
        self._durable_bridge = SimpleNamespace(lookup_retry_circuit=AsyncMock(return_value=None))
        self._http_bridge_retry_circuits: dict[_HTTPBridgeSessionKey, _HTTPBridgeRetryCircuitState] = {}
        _initialize_http_bridge_retry_circuit(self)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> _CircuitHarness:
    # Replace this module's clock, not asyncio's process-wide monotonic clock.
    monkeypatch.setattr(circuit_module, "time", SimpleNamespace(monotonic=lambda: 100.0, time=lambda: 1000.0))
    return _CircuitHarness()


@pytest.fixture
def session() -> _HTTPBridgeSession:
    return cast(
        _HTTPBridgeSession,
        SimpleNamespace(key=_HTTPBridgeSessionKey("session_header", "synthetic-gate", None)),
    )


def _state(*, cooldown: float = 0.0, half_open: float = 200.0) -> _HTTPBridgeRetryCircuitState:
    return _HTTPBridgeRetryCircuitState(
        consecutive_failures=2,
        cooldown_until=cooldown,
        half_open_until=half_open,
        last_detail="stream_incomplete",
        last_touched_monotonic=100.0,
    )


async def test_half_open_refusal_does_not_imply_a_future_cooldown(
    harness: _CircuitHarness, session: _HTTPBridgeSession
) -> None:
    harness._http_bridge_retry_circuits[session.key] = _state()

    assert await harness._http_bridge_precreated_retry_allowed(session) is False
    assert await harness._http_bridge_precreated_retry_cooldown_seconds(session) == 0.0
    assert harness._http_bridge_retry_circuits[session.key].half_open_until == 200.0


@pytest.mark.parametrize(
    ("flag", "allowed"),
    [
        ("allow_fresh_hard_account_switch", True),
        ("allow_proof_gated_continuity_replay", True),
        ("allow_operation_fenced_continuity_replay", False),
    ],
)
async def test_existing_half_open_allowance_flags_are_not_interchangeable(
    harness: _CircuitHarness, session: _HTTPBridgeSession, flag: str, allowed: bool
) -> None:
    state = _state()
    harness._http_bridge_retry_circuits[session.key] = state

    result = await harness._http_bridge_precreated_retry_allowed(session, **{flag: True})

    assert result is allowed
    assert state.cooldown_until == 0.0
    assert state.half_open_until == 200.0
    assert state.consecutive_failures == 2


@pytest.mark.parametrize(
    "flag",
    [
        "allow_fresh_hard_account_switch",
        "allow_proof_gated_continuity_replay",
        "allow_operation_fenced_continuity_replay",
    ],
)
async def test_existing_future_cooldown_allowances_do_not_clear_the_source_circuit(
    harness: _CircuitHarness, session: _HTTPBridgeSession, flag: str
) -> None:
    state = _state(cooldown=145.0, half_open=0.0)
    harness._http_bridge_retry_circuits[session.key] = state

    assert await harness._http_bridge_precreated_retry_allowed(session, **{flag: True}) is True
    assert state.cooldown_until == 145.0
    assert state.consecutive_failures == 2
    assert await harness._http_bridge_precreated_retry_allowed(session) is False


async def test_concurrent_ordinary_calls_reserve_only_one_expired_cooldown_probe(
    harness: _CircuitHarness, session: _HTTPBridgeSession
) -> None:
    state = _state(cooldown=99.0, half_open=0.0)
    harness._http_bridge_retry_circuits[session.key] = state

    results = await asyncio.gather(
        harness._http_bridge_precreated_retry_allowed(session),
        harness._http_bridge_precreated_retry_allowed(session),
    )

    assert sorted(results) == [False, True]
    assert state.cooldown_until == 0.0
    assert state.half_open_until == 100.0 + circuit_module._HTTP_BRIDGE_RETRY_CIRCUIT_HALF_OPEN_LEASE_SECONDS
    assert await harness._http_bridge_precreated_retry_cooldown_seconds(session) == 0.0


async def test_durable_cooldown_is_authoritative_before_the_admission_decision(
    harness: _CircuitHarness, session: _HTTPBridgeSession
) -> None:
    lookup = harness._durable_bridge.lookup_retry_circuit
    lookup.return_value = DurableBridgeRetryCircuitSnapshot(
        session_key_kind="session_header",
        session_key_hash="synthetic-hash",
        api_key_scope="anonymous",
        consecutive_failures=2,
        cooldown_until_epoch=1042.0,
        last_detail="stream_incomplete",
        updated_at_epoch=1000.0,
        admission_generation=0,
    )

    assert await harness._http_bridge_precreated_retry_allowed(session) is False
    state = harness._http_bridge_retry_circuits[session.key]
    assert state.cooldown_until == 142.0
    assert state.last_detail == "stream_incomplete"
    lookup.assert_awaited_once_with(
        session_key_kind="session_header", session_key_value="synthetic-gate", api_key_id=None
    )


async def test_lookup_failure_keeps_local_half_open_occupancy(
    harness: _CircuitHarness, session: _HTTPBridgeSession
) -> None:
    state = _state()
    harness._http_bridge_retry_circuits[session.key] = state
    harness._durable_bridge.lookup_retry_circuit.side_effect = RuntimeError("synthetic lookup unavailable")

    assert await harness._http_bridge_precreated_retry_allowed(session) is False
    assert state.cooldown_until == 0.0
    assert state.half_open_until == 200.0
    assert state.consecutive_failures == 2


async def test_soft_affinity_does_not_read_or_claim_a_hard_key_circuit(harness: _CircuitHarness) -> None:
    soft_session = cast(
        _HTTPBridgeSession,
        SimpleNamespace(key=_HTTPBridgeSessionKey("prompt_cache", "synthetic-soft", None, strength="soft")),
    )

    assert await harness._http_bridge_precreated_retry_allowed(soft_session) is True
    harness._durable_bridge.lookup_retry_circuit.assert_not_awaited()
    assert harness._http_bridge_retry_circuits == {}


@pytest.mark.parametrize(
    ("cooldown", "half_open", "reason", "remaining"),
    [
        (145.0, 0.0, "cooldown", 45.0),
        (0.0, 200.0, "half_open_busy", 0.0),
    ],
)
async def test_typed_decision_distinguishes_denials_from_the_authoritative_snapshot(
    harness: _CircuitHarness,
    session: _HTTPBridgeSession,
    cooldown: float,
    half_open: float,
    reason: str,
    remaining: float,
) -> None:
    harness._http_bridge_retry_circuits[session.key] = _state(cooldown=cooldown, half_open=half_open)

    decision = await harness._http_bridge_precreated_retry_decision(session)

    assert decision.allowed is False
    assert decision.blocked_reason == reason
    assert decision.cooldown_remaining_seconds == remaining
    harness._durable_bridge.lookup_retry_circuit.assert_awaited_once()


@pytest.mark.parametrize(
    "flag",
    [
        "allow_fresh_hard_account_switch",
        "allow_proof_gated_continuity_replay",
        "allow_operation_fenced_continuity_replay",
    ],
)
async def test_typed_allowance_retains_cooldown_without_inventing_a_denial(
    harness: _CircuitHarness, session: _HTTPBridgeSession, flag: str
) -> None:
    harness._http_bridge_retry_circuits[session.key] = _state(cooldown=145.0, half_open=0.0)

    decision = await harness._http_bridge_precreated_retry_decision(session, **{flag: True})

    assert decision.allowed is True
    assert decision.blocked_reason is None
    assert decision.cooldown_remaining_seconds == 45.0
    assert harness._http_bridge_retry_circuits[session.key].cooldown_until == 145.0


async def test_boolean_adapter_does_not_evaluate_or_reserve_twice(
    harness: _CircuitHarness, session: _HTTPBridgeSession
) -> None:
    harness._http_bridge_retry_circuits[session.key] = _state(cooldown=99.0, half_open=0.0)

    assert await harness._http_bridge_precreated_retry_allowed(session) is True
    harness._durable_bridge.lookup_retry_circuit.assert_awaited_once()
    assert await harness._http_bridge_precreated_retry_allowed(session) is False
    assert harness._durable_bridge.lookup_retry_circuit.await_count == 2


async def test_typed_decision_preserves_existing_local_fallback_on_lookup_failure(
    harness: _CircuitHarness, session: _HTTPBridgeSession
) -> None:
    harness._durable_bridge.lookup_retry_circuit.side_effect = RuntimeError("synthetic lookup unavailable")

    decision = await harness._http_bridge_precreated_retry_decision(session)

    assert decision.allowed is True
    assert decision.blocked_reason is None
    assert decision.cooldown_remaining_seconds == 0.0
    assert harness._http_bridge_retry_circuits == {}
