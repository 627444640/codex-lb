"""Admission breaker trip, recovery, and single pre-output failover."""

from __future__ import annotations

import time

from app.modules.proxy._load_balancer.admission_breaker import (
    AdmissionBreakerPolicy,
    AdmissionFailoverAction,
    _failover_mark,
    authored_pre_output_close,
    blocks_new_assignment,
    counts_as_admission_failure,
    current_admission_failover,
    filter_admission_breaker_candidates,
    note_admission_failover,
    plan_admission_failover,
    record_admission_failure_locked,
    record_admission_success_locked,
    reserve_half_open_probe_locked,
    snapshot_admission_breaker,
)
from app.modules.proxy._load_balancer.types import RuntimeState
from app.modules.proxy.service import _WEBSOCKET_TRANSPARENT_REPLAY_ERROR_CODES

_POLICY = AdmissionBreakerPolicy()


class _State:
    def __init__(self, account_id: str) -> None:
        self.account_id = account_id


def test_three_consecutive_failures_open_the_breaker() -> None:
    runtime = RuntimeState()
    now = 1_000.0
    assert record_admission_failure_locked(runtime, now, _POLICY, account_id="a") is False
    assert record_admission_failure_locked(runtime, now + 1, _POLICY, account_id="a") is False
    assert record_admission_failure_locked(runtime, now + 2, _POLICY, account_id="a") is True
    assert blocks_new_assignment(runtime, now + 2, _POLICY) is True
    snapshot = snapshot_admission_breaker(runtime, now + 2, _POLICY)
    assert snapshot.state == "open"
    assert snapshot.open_until == now + 2 + _POLICY.open_seconds


def test_three_failures_inside_the_window_trip_despite_a_success() -> None:
    runtime = RuntimeState()
    now = 2_000.0
    record_admission_failure_locked(runtime, now, _POLICY, account_id="a")
    record_admission_failure_locked(runtime, now + 1, _POLICY, account_id="a")
    record_admission_success_locked(runtime, now + 2, _POLICY, account_id="a")
    assert runtime.admission_consecutive_failures == 0
    assert record_admission_failure_locked(runtime, now + 3, _POLICY, account_id="a") is True
    assert blocks_new_assignment(runtime, now + 3, _POLICY) is True


def test_client_errors_do_not_count() -> None:
    for code in (
        "client_disconnected",
        "context_length_exceeded",
        "invalid_request",
        "invalid_request_error",
        "rate_limit_exceeded",
        "quota_exceeded",
    ):
        assert counts_as_admission_failure(code, 400, pre_first_output_close=True) is False
    assert counts_as_admission_failure("invalid_request_error", None, pre_first_output_close=False) is False
    assert counts_as_admission_failure("stream_incomplete", None, pre_first_output_close=False) is False
    assert counts_as_admission_failure("upstream_error", 404, pre_first_output_close=False) is False


def test_authored_close_before_output_counts_and_frameless_close_does_not() -> None:
    assert authored_pre_output_close(close_code=1000, message=None) is True
    assert authored_pre_output_close(close_code=None, message="upstream closed close_code=1000") is True
    assert authored_pre_output_close(close_code=1006, message="close_code=1006") is False
    assert authored_pre_output_close(close_code=1011, message="close_code=1011") is False
    assert authored_pre_output_close(close_code=None, message="connection reset") is False
    assert counts_as_admission_failure("stream_incomplete", None, pre_first_output_close=True) is True
    assert counts_as_admission_failure("server_error", 200, pre_first_output_close=False) is True
    assert counts_as_admission_failure("server_is_overloaded", None, pre_first_output_close=False) is True


def test_half_open_probe_failure_reopens_and_success_recovers() -> None:
    runtime = RuntimeState()
    now = 3_000.0
    for offset in (0, 1, 2):
        record_admission_failure_locked(runtime, now + offset, _POLICY, account_id="a")
    open_until = runtime.admission_open_until
    assert open_until is not None
    assert blocks_new_assignment(runtime, open_until - 1, _POLICY) is True
    assert snapshot_admission_breaker(runtime, open_until + 1, _POLICY).state == "half_open"
    assert reserve_half_open_probe_locked(runtime, open_until + 1, _POLICY) is True
    assert reserve_half_open_probe_locked(runtime, open_until + 1, _POLICY) is False
    record_admission_failure_locked(runtime, open_until + 2, _POLICY, account_id="a")
    assert blocks_new_assignment(runtime, open_until + 2, _POLICY) is True
    later = runtime.admission_open_until
    assert later is not None
    assert reserve_half_open_probe_locked(runtime, later + 1, _POLICY) is True
    record_admission_success_locked(runtime, later + 2, _POLICY, account_id="a")
    assert snapshot_admission_breaker(runtime, later + 2, _POLICY).state == "closed"


def test_success_while_open_does_not_close() -> None:
    runtime = RuntimeState()
    now = 4_000.0
    for offset in (0, 1, 2):
        record_admission_failure_locked(runtime, now + offset, _POLICY, account_id="a")
    record_admission_success_locked(runtime, now + 3, _POLICY, account_id="a")
    assert blocks_new_assignment(runtime, now + 3, _POLICY) is True


def test_filter_drops_open_accounts_and_does_not_return_the_original_list() -> None:
    sick = RuntimeState(admission_open_until=time.time() + 60)
    healthy = RuntimeState()
    states = [_State("sick"), _State("healthy")]
    runtime = {"sick": sick, "healthy": healthy}
    kept = filter_admission_breaker_candidates(states, runtime, now=time.time(), policy=_POLICY)
    assert [state.account_id for state in kept] == ["healthy"]
    assert kept is not states
    only_sick = filter_admission_breaker_candidates([_State("sick")], runtime, now=time.time(), policy=_POLICY)
    assert only_sick == []


def test_failover_is_once_before_output_and_stops_after() -> None:
    def decide(
        *,
        error_code: str = "server_error",
        http_status: int | None = 500,
        downstream_visible: bool = False,
        already_retried: bool = False,
        continuity_pinned: bool = False,
        attempts_remaining: bool = True,
        pre_first_output_close: bool = False,
        policy: AdmissionBreakerPolicy | None = _POLICY,
    ) -> str:
        return plan_admission_failover(
            error_code=error_code,
            http_status=http_status,
            downstream_visible=downstream_visible,
            already_retried=already_retried,
            continuity_pinned=continuity_pinned,
            attempts_remaining=attempts_remaining,
            pre_first_output_close=pre_first_output_close,
            policy=policy,
        )

    assert decide() == AdmissionFailoverAction.FAILOVER_ONCE
    assert decide(already_retried=True) == AdmissionFailoverAction.SURFACE
    assert decide(downstream_visible=True) == AdmissionFailoverAction.SURFACE
    assert decide(continuity_pinned=True) == AdmissionFailoverAction.SURFACE
    assert decide(attempts_remaining=False) == AdmissionFailoverAction.SURFACE
    assert decide(error_code="rate_limit_exceeded", http_status=429) == AdmissionFailoverAction.PASSTHROUGH
    assert decide(policy=AdmissionBreakerPolicy(enabled=False)) == AdmissionFailoverAction.PASSTHROUGH


def test_failover_mark_records_the_first_account_only() -> None:
    token = _failover_mark.set(None)
    try:
        assert current_admission_failover() is None
        note_admission_failover("account-a")
        note_admission_failover("account-b")
        mark = current_admission_failover()
        assert mark is not None
        assert mark.from_account_id == "account-a"
    finally:
        _failover_mark.reset(token)


def test_websocket_transparent_replay_includes_server_error() -> None:
    assert "server_error" in _WEBSOCKET_TRANSPARENT_REPLAY_ERROR_CODES
    assert "client_disconnected" not in _WEBSOCKET_TRANSPARENT_REPLAY_ERROR_CODES
