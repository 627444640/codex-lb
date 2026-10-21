"""Per-account admission circuit breaker for upstream 5xx bursts.

The transport-level breaker in ``app.core.resilience.circuit_breaker`` stays
off by default and does not remove one sick account from selection. Overload
backoff only deprioritizes ``server_is_overloaded`` and is cleared, in
practice, by successes on warm sessions. This module counts the upstream
admission failures that dominated the v1.24.3 production logs and holds the
account out of *new* assignment until a half-open probe succeeds.

Replica-local, like overload backoff and the error-rate window. Hard
continuity (a ``previous_response_id`` owned by the account, a file pin, or
``single_account``) is not moved by this module.
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config.settings import get_settings
from app.modules.proxy._load_balancer.response_retry_budget import (
    _transparent_retry_used as _transparent_retry_used,
)
from app.modules.proxy._load_balancer.response_retry_budget import (
    mark_transparent_retry as mark_transparent_retry,
)
from app.modules.proxy._load_balancer.response_retry_budget import (
    reset_transparent_retry as reset_transparent_retry,
)
from app.modules.proxy._load_balancer.response_retry_budget import (
    transparent_retry_used as transparent_retry_used,
)
from app.modules.proxy._load_balancer.types import RuntimeState

logger = logging.getLogger(__name__)

AdmissionPhase = Literal["closed", "open", "half_open"]

# Named upstream admission failures. These count even when the HTTP status is
# 200, because streamed ``server_error`` / ``server_is_overloaded`` events
# arrive after the response has already started.
ADMISSION_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "server_error",
        "server_is_overloaded",
        "overloaded_error",
    }
)

# Client and quota failures must never open the breaker.
ADMISSION_NON_TRIP_CODES: frozenset[str] = frozenset(
    {
        "client_disconnected",
        "context_length_exceeded",
        "invalid_request",
        "invalid_request_error",
        "rate_limit_exceeded",
        "usage_limit_reached",
        "insufficient_quota",
        "quota_exceeded",
        "usage_not_included",
    }
)

# Close code 1000 before any output is the production rejection signature.
# 1006 is synthesized locally. 1011 keeps the existing owner-preserving replay.
_CLOSE_CODE_IN_MESSAGE = re.compile(r"close_code=(\d+)")
_PROBE_STALE_SECONDS = 30.0
_JITTER_MIN_SECONDS = 0.05
_JITTER_MAX_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class AdmissionBreakerPolicy:
    """Operator knobs. Defaults are the zero-config working behavior."""

    enabled: bool = True
    failure_threshold: int = 3
    window_seconds: float = 60.0
    open_seconds: float = 300.0

    @classmethod
    def from_settings(cls) -> AdmissionBreakerPolicy:
        settings = get_settings()
        # Missing attributes stay off. Production ``Settings`` defines them
        # (enabled by default). Partial test doubles that omit the fields keep
        # the previous retry behavior.
        return cls(
            enabled=_settings_bool(settings, "account_admission_breaker_enabled", False),
            failure_threshold=max(1, _settings_int(settings, "account_admission_breaker_failure_threshold", 3)),
            window_seconds=_settings_float(settings, "account_admission_breaker_window_seconds", 60.0),
            open_seconds=_settings_float(settings, "account_admission_breaker_open_seconds", 300.0),
        )


@dataclass(frozen=True, slots=True)
class AdmissionFailoverMark:
    from_account_id: str


@dataclass(frozen=True, slots=True)
class AdmissionBreakerSnapshot:
    state: AdmissionPhase
    consecutive_failures: int
    window_failures: int
    open_until: float | None
    probe_in_flight: bool


class AdmissionFailoverAction:
    PASSTHROUGH = "passthrough"
    FAILOVER_ONCE = "failover_once"
    SURFACE = "surface"


_failover_mark: ContextVar[AdmissionFailoverMark | None] = ContextVar("admission_failover_mark", default=None)
# Qualifying failures already counted for this attempt, so one close is not applied twice.
_admission_counted: ContextVar[frozenset[tuple[str, str]]] = ContextVar(
    "admission_counted",
    default=frozenset(),
)


def reset_admission_request_context() -> None:
    """Drop admission marks so the next request starts with a full resend budget."""

    reset_transparent_retry()
    reset_admission_failure_dedupe()
    _failover_mark.set(None)


def reset_admission_failure_dedupe() -> None:
    """Allow the next attempt on this request to count a new qualifying failure."""

    _admission_counted.set(frozenset())


def note_admission_failover(from_account_id: str, request_id: str | None = None) -> None:
    """Remember that this request already failed over once, for the request log."""

    mark_transparent_retry(request_id)
    if _failover_mark.get() is None:
        _failover_mark.set(AdmissionFailoverMark(from_account_id=from_account_id))


def note_soft_preferred_admission_failover(
    from_account_id: str,
    request_id: str | None = None,
    *,
    logged_account_id: str | None = None,
    history_replay_reason: str | None = None,
) -> None:
    """Record one soft-preferred move off an admission-blocked account."""

    note_admission_failover(from_account_id, request_id=request_id)
    logger.warning(
        "admission_failover reason=account_admission_breaker_open from_account_id=%s "
        "request_id=%s history_replay_reason=%s",
        logged_account_id if logged_account_id is not None else from_account_id,
        request_id,
        history_replay_reason or "-",
    )


def current_admission_failover() -> AdmissionFailoverMark | None:
    return _failover_mark.get()


# Set only for the selection that dropped a soft-preferred account. Cleared at
# the start of each budgeted selection so a later request on the same task
# does not inherit the exclusion.
_soft_preferred_excluded: ContextVar[bool] = ContextVar("soft_preferred_admission_excluded", default=False)


def reset_soft_preferred_admission_exclusion() -> None:
    """Forget a soft-preferred exclusion from an earlier selection on this task."""

    _soft_preferred_excluded.set(False)


def drop_soft_preferred(scope: Mapping[str, Any]) -> bool:
    """Exclude a soft-preferred account whose admission breaker blocks assignment.

    ``scope`` is the selecting method's ``locals()``. Returns True when that
    account must not receive the turn. Ownership pins and ``single_account``
    stay on the preferred path.
    """

    preferred_account_id = scope["preferred_account_id"]
    if (
        not isinstance(preferred_account_id, str)
        or scope["required_preferred_account"] is True
        or scope["routing_strategy"] == "single_account"
    ):
        return False
    excluded = scope["excluded_account_ids_set"]
    log_account_id = scope["log_account_id"]
    balancer = scope["self"]._load_balancer
    if not _account_admission_blocks(balancer, preferred_account_id):
        return False
    excluded.add(preferred_account_id)
    logged_account_id = log_account_id(preferred_account_id)
    note_soft_preferred_admission_failover(
        preferred_account_id,
        request_id=scope["request_id"],
        logged_account_id=logged_account_id if isinstance(logged_account_id, str) else None,
    )
    _soft_preferred_excluded.set(True)
    return True


async def reject_excluded_or_admission(scope: Mapping[str, Any], log: logging.Logger) -> Any:
    """Return a terminal selection when the chosen account cannot be used.

    A soft-preferred admission exclusion reports ``account_admission_breaker_open``
    and releases a lease. Any other excluded account keeps the historical
    ``no_accounts`` result and its lease.
    """

    from app.modules.proxy.load_balancer import AccountSelection

    selection = scope["selection"]
    excluded = scope["excluded_account_ids_set"]
    log_account_id = scope["log_account_id"]
    account = selection.account
    account_excluded = account is not None and account.id in excluded
    if _soft_preferred_excluded.get() and (account is None or account_excluded):
        if selection.lease is not None:
            await scope["self"]._load_balancer.release_account_lease(selection.lease)
        preferred_account_id = scope["preferred_account_id"]
        logged_account_id = log_account_id(preferred_account_id if isinstance(preferred_account_id, str) else None)
        log.warning(
            "Admission breaker blocked new assignment account_id=%s",
            logged_account_id,
        )
        return AccountSelection(
            account=None,
            error_message="No available accounts",
            error_code="account_admission_breaker_open",
        )
    if account_excluded:
        log.warning(
            "Proxy account selection returned excluded account request_id=%s kind=%s request_stage=%s "
            "account_id=%s excluded_count=%s",
            scope["request_id"],
            scope["kind"],
            scope["request_stage"],
            log_account_id(account.id),
            len(excluded),
        )
        return AccountSelection(
            account=None,
            error_message="No active accounts available",
            error_code="no_accounts",
        )
    return None


def _account_admission_blocks(balancer: object, account_id: str) -> bool:
    from app.modules.proxy.conversation_history import account_admission_blocks

    return account_admission_blocks(balancer, account_id)


def admission_retry_jitter_seconds() -> float:
    return random.uniform(_JITTER_MIN_SECONDS, _JITTER_MAX_SECONDS)


def authored_pre_output_close(*, close_code: int | None, message: str | None) -> bool:
    """True when upstream closed cleanly (1000) before any output.

    That is the production rejection signature. Missing and 1006 codes are
    local/frame-less. Other authored codes, including 1011, keep their
    existing owner-preserving replay and are not admission failures.
    """

    code = close_code
    if code is None and message:
        match = _CLOSE_CODE_IN_MESSAGE.search(message)
        if match is not None:
            code = int(match.group(1))
    return code == 1000


def counts_as_admission_failure(
    error_code: str,
    http_status: int | None,
    *,
    pre_first_output_close: bool,
) -> bool:
    if error_code in ADMISSION_NON_TRIP_CODES:
        return False
    if error_code in ADMISSION_FAILURE_CODES:
        return True
    if error_code == "stream_incomplete" and pre_first_output_close:
        return True
    return http_status is not None and http_status >= 500


def plan_admission_failover(
    *,
    error_code: str,
    http_status: int | None,
    downstream_visible: bool,
    already_retried: bool,
    continuity_pinned: bool,
    attempts_remaining: bool,
    pre_first_output_close: bool,
    policy: AdmissionBreakerPolicy | None = None,
) -> str:
    """Decide whether a pre-output admission failure may move once.

    ``surface`` means the client sees the failure. That includes output that
    already started, a second failure on the same request, and any request
    pinned to the account that just failed (``previous_response_id``, file
    pin, or single-account routing). A disabled policy leaves the existing
    retry path unchanged.
    """

    effective = policy if policy is not None else AdmissionBreakerPolicy.from_settings()
    if not effective.enabled:
        return AdmissionFailoverAction.PASSTHROUGH
    if not counts_as_admission_failure(
        error_code,
        http_status,
        pre_first_output_close=pre_first_output_close,
    ):
        return AdmissionFailoverAction.PASSTHROUGH
    if downstream_visible or already_retried or continuity_pinned or not attempts_remaining:
        return AdmissionFailoverAction.SURFACE
    return AdmissionFailoverAction.FAILOVER_ONCE


def expire_stale_probe(runtime: RuntimeState, now: float) -> None:
    started = runtime.admission_probe_started_at
    if runtime.admission_probe_in_flight and started is not None and now - started >= _PROBE_STALE_SECONDS:
        runtime.admission_probe_in_flight = False
        runtime.admission_probe_started_at = None


def admission_phase(runtime: RuntimeState | None, now: float, policy: AdmissionBreakerPolicy) -> AdmissionPhase:
    if runtime is None or not policy.enabled:
        return "closed"
    expire_stale_probe(runtime, now)
    open_until = runtime.admission_open_until
    if open_until is None:
        return "closed"
    if now < open_until:
        return "open"
    if not runtime.admission_half_open_logged:
        runtime.admission_half_open_logged = True
        logger.info("Admission breaker half-open open_until=%s", open_until)
    return "half_open"


def blocks_new_assignment(runtime: RuntimeState | None, now: float, policy: AdmissionBreakerPolicy) -> bool:
    phase = admission_phase(runtime, now, policy)
    if phase == "open":
        return True
    if phase == "half_open" and runtime is not None and runtime.admission_probe_in_flight:
        return True
    return False


def filter_admission_breaker_candidates(
    states: list,
    runtime_by_account_id: dict[str, RuntimeState] | object,
    *,
    now: float,
    policy: AdmissionBreakerPolicy | None = None,
) -> list:
    """Drop accounts that must not receive a new assignment.

    Returns the same list object when nothing is removed. Returns an empty
    list when every candidate is blocked so callers do not fall back onto the
    open account. A half-open account with no probe in flight stays eligible
    for the single recovery probe.
    """

    effective = policy if policy is not None else AdmissionBreakerPolicy.from_settings()
    if not effective.enabled or not isinstance(runtime_by_account_id, dict):
        return states
    kept = [
        state
        for state in states
        if not blocks_new_assignment(runtime_by_account_id.get(state.account_id), now, effective)
    ]
    if len(kept) == len(states):
        return states
    return kept


def _window_failures(runtime: RuntimeState, now: float, window_seconds: float) -> list[float]:
    window_start = now - window_seconds
    return [stamp for stamp in (runtime.admission_failure_times or ()) if stamp > window_start]


def record_admission_failure_locked(
    runtime: RuntimeState,
    now: float,
    policy: AdmissionBreakerPolicy,
    *,
    account_id: str,
) -> bool:
    """Record one qualifying failure. Returns True when the breaker opens or re-opens."""

    if not policy.enabled:
        return False
    phase = admission_phase(runtime, now, policy)
    runtime.admission_probe_in_flight = False
    runtime.admission_probe_started_at = None
    if phase == "open":
        # Requests already in flight when the breaker opened must not keep
        # pushing the recovery time out.
        return False
    if phase == "half_open":
        _open_breaker(runtime, now, policy, account_id=account_id, reason="probe_failed")
        return True
    runtime.admission_consecutive_failures += 1
    recent = _window_failures(runtime, now, policy.window_seconds)
    recent.append(now)
    runtime.admission_failure_times = recent
    if runtime.admission_consecutive_failures >= policy.failure_threshold or len(recent) >= policy.failure_threshold:
        _open_breaker(runtime, now, policy, account_id=account_id, reason="threshold")
        return True
    return False


def record_admission_success_locked(
    runtime: RuntimeState,
    now: float,
    policy: AdmissionBreakerPolicy,
    *,
    account_id: str,
) -> None:
    """A success resets the consecutive counter.

    A success while the breaker is open does not close it: warm-session
    successes were masking the sick account. Only the half-open probe
    success recovers the account.
    """

    if not policy.enabled:
        return
    phase = admission_phase(runtime, now, policy)
    runtime.admission_probe_in_flight = False
    runtime.admission_probe_started_at = None
    if phase == "open":
        return
    if phase == "half_open":
        runtime.admission_open_until = None
        runtime.admission_failure_times = []
        runtime.admission_consecutive_failures = 0
        logger.warning("Account admission breaker recovered account_id=%s", account_id)
        return
    runtime.admission_consecutive_failures = 0


def snapshot_admission_breaker(
    runtime: RuntimeState | None,
    now: float,
    policy: AdmissionBreakerPolicy,
) -> AdmissionBreakerSnapshot:
    phase = admission_phase(runtime, now, policy)
    if runtime is None:
        return AdmissionBreakerSnapshot(
            state=phase,
            consecutive_failures=0,
            window_failures=0,
            open_until=None,
            probe_in_flight=False,
        )
    recent = _window_failures(runtime, now, policy.window_seconds) if policy.enabled else []
    open_until = runtime.admission_open_until if phase != "closed" else None
    return AdmissionBreakerSnapshot(
        state=phase,
        consecutive_failures=runtime.admission_consecutive_failures,
        window_failures=len(recent),
        open_until=open_until,
        probe_in_flight=bool(runtime.admission_probe_in_flight) and phase == "half_open",
    )


def reserve_half_open_probe_locked(runtime: RuntimeState, now: float, policy: AdmissionBreakerPolicy) -> bool:
    """Return True when this caller may send the half-open probe (or the account is closed)."""

    if not policy.enabled:
        return True
    phase = admission_phase(runtime, now, policy)
    if phase == "closed":
        return True
    if phase == "open":
        return False
    if runtime.admission_probe_in_flight:
        return False
    runtime.admission_probe_in_flight = True
    runtime.admission_probe_started_at = now
    return True


def _open_breaker(
    runtime: RuntimeState,
    now: float,
    policy: AdmissionBreakerPolicy,
    *,
    account_id: str,
    reason: str,
) -> None:
    runtime.admission_open_until = now + policy.open_seconds
    runtime.admission_consecutive_failures = 0
    runtime.admission_failure_times = []
    runtime.admission_probe_in_flight = False
    runtime.admission_probe_started_at = None
    runtime.admission_half_open_logged = False
    logger.warning(
        "Account admission breaker opened account_id=%s reason=%s open_seconds=%.0f threshold=%d window_seconds=%.0f",
        account_id,
        reason,
        policy.open_seconds,
        policy.failure_threshold,
        policy.window_seconds,
    )


def wall_open_until(open_until: float | None) -> float | None:
    """``open_until`` is already ``time.time()`` seconds."""

    return open_until


def monotonic_now() -> float:
    return time.time()


def sticky_admission_alternatives(
    states: list,
    runtime_by_account_id: dict[str, RuntimeState] | object | None,
    *,
    owner_account_id: str,
    now: float,
    routing_strategy: str,
    policy: AdmissionBreakerPolicy | None = None,
) -> list | None:
    """Siblings that may serve a soft sticky turn while the owner is open.

    ``None`` means the owner stays (breaker closed, disabled, single-account
    routing, or no runtime). An empty list means the owner is blocked and no
    unblocked sibling is in the pool.
    """

    effective = policy if policy is not None else AdmissionBreakerPolicy.from_settings()
    if routing_strategy == "single_account" or not effective.enabled:
        return None
    if not isinstance(runtime_by_account_id, dict):
        return None
    if not blocks_new_assignment(runtime_by_account_id.get(owner_account_id), now, effective):
        return None
    return [
        state
        for state in states
        if state.account_id != owner_account_id
        and not blocks_new_assignment(runtime_by_account_id.get(state.account_id), now, effective)
    ]


async def record_upstream_admission_failure(
    balancer: Any,
    account: Any,
    *,
    error_code: str,
    http_status: int | None = None,
    pre_first_output_close: bool = False,
) -> None:
    """Count one qualifying failure on the balancer that owns ``_runtime``.

    No-op for test doubles that do not expose the runtime map, and for errors
    that must not open the breaker.
    """

    if not counts_as_admission_failure(
        error_code,
        http_status,
        pre_first_output_close=pre_first_output_close,
    ):
        return
    account_id = getattr(account, "id", None)
    if not isinstance(account_id, str) or not account_id:
        return
    runtime_map = getattr(balancer, "_runtime", None)
    lock_factory = getattr(balancer, "_get_account_lock", None)
    if not isinstance(runtime_map, dict) or lock_factory is None:
        return
    policy = AdmissionBreakerPolicy.from_settings()
    if not policy.enabled:
        return
    counted_key = (account_id, error_code)
    counted = _admission_counted.get()
    if counted_key in counted:
        return
    _admission_counted.set(frozenset((*counted, counted_key)))
    lock = await lock_factory(account_id)
    async with lock:
        runtime = runtime_map.setdefault(account_id, RuntimeState())
        record_admission_failure_locked(runtime, time.time(), policy, account_id=account_id)


def _settings_bool(settings: Any, name: str, default: bool) -> bool:
    value = getattr(settings, name, default)
    if isinstance(value, bool):
        return value
    return default


def _settings_int(settings: Any, name: str, default: int) -> int:
    value = getattr(settings, name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _settings_float(settings: Any, name: str, default: float) -> float:
    value = getattr(settings, name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)
