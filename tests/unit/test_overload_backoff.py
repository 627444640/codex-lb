from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

import app.modules.proxy._service.streaming.helpers as streaming_helpers_module
from app.core.balancer import ERROR_BACKOFF_THRESHOLD
from app.core.balancer.logic import (
    HEALTH_TIER_DRAINING,
    HEALTH_TIER_PROBING,
    ROUTING_POLICY_PRESERVE,
    AccountState,
    RoutingCost,
    RoutingStrategy,
    select_account,
)
from app.core.config.settings import get_settings
from app.core.crypto import TokenEncryptor
from app.db.models import Account, AccountStatus, StickySessionKind
from app.modules.proxy._load_balancer.overload_backoff import (
    OVERLOAD_BACKOFF_BASE_SECONDS,
    OVERLOAD_BACKOFF_MAX_SECONDS,
    OVERLOAD_ISOLATION_TRIP_LEVEL,
    OVERLOAD_LEVEL_DECAY_SECONDS,
    OVERLOAD_MAX_LEVEL,
    OVERLOAD_TRIP_COUNT,
    OVERLOAD_WINDOW_SECONDS,
    OverloadIsolationPolicy,
    filter_overload_backoff_candidates,
    isolation_substitute_seed,
    overload_backoff_active,
    overload_backoff_seconds,
    overload_isolation_active,
    record_overload_rejection_locked,
    record_upstream_overload,
    sticky_owner_isolation_reroute_pool,
)
from app.modules.proxy._load_balancer.types import RuntimeState
from app.modules.proxy._service.streaming.retry import _transient_retry_error_code
from app.modules.proxy._service.support import _TransientStreamError
from app.modules.proxy.load_balancer import LoadBalancer
from tests.unit.test_load_balancer_concurrency import (
    _repo_factory,
    _StubAccountsRepository,
    _StubUsageRepository,
)

pytestmark = pytest.mark.unit


@dataclass
class VirtualClock:
    epoch_value: float

    def time(self) -> float:
        return self.epoch_value

    def advance(self, seconds: float) -> None:
        self.epoch_value += seconds


@pytest.fixture
def wall_clock(monkeypatch: pytest.MonkeyPatch) -> VirtualClock:
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    return clock


def _make_account(account_id: str) -> Account:
    encryptor = TokenEncryptor()
    return Account(
        id=account_id,
        chatgpt_account_id=f"workspace-{account_id}",
        email=f"{account_id}@example.com",
        plan_type="plus",
        access_token_encrypted=encryptor.encrypt("access"),
        refresh_token_encrypted=encryptor.encrypt("refresh"),
        id_token_encrypted=encryptor.encrypt("id"),
        last_refresh=datetime.now(tz=timezone.utc),
        status=AccountStatus.ACTIVE,
        deactivation_reason=None,
    )


def _state(account_id: str) -> AccountState:
    return AccountState(account_id=account_id, status=AccountStatus.ACTIVE, used_percent=0.0)


def test_window_trips_only_on_the_third_rejection_inside_the_window() -> None:
    runtime = RuntimeState()
    assert record_overload_rejection_locked(runtime, 1000.0) is None
    assert record_overload_rejection_locked(runtime, 1010.0) is None
    assert not overload_backoff_active(runtime, 1010.0)

    deadline = record_overload_rejection_locked(runtime, 1020.0)

    assert deadline == pytest.approx(1020.0 + OVERLOAD_BACKOFF_BASE_SECONDS)
    assert runtime.overload_backoff_level == 1
    assert runtime.overload_rejections == []
    assert overload_backoff_active(runtime, 1020.0 + OVERLOAD_BACKOFF_BASE_SECONDS - 1)
    assert not overload_backoff_active(runtime, 1020.0 + OVERLOAD_BACKOFF_BASE_SECONDS)


def test_rejections_outside_the_window_do_not_count() -> None:
    runtime = RuntimeState()
    record_overload_rejection_locked(runtime, 0.0)
    record_overload_rejection_locked(runtime, 1.0)
    # Two stale rejections plus one fresh one: below the trip count.
    assert record_overload_rejection_locked(runtime, OVERLOAD_WINDOW_SECONDS + 5.0) is None
    assert runtime.overload_rejections == [OVERLOAD_WINDOW_SECONDS + 5.0]


def test_repeated_trips_grow_exponentially_and_are_capped() -> None:
    runtime = RuntimeState()
    now = 0.0
    deadlines: list[float] = []
    for _ in range(6):
        for _ in range(OVERLOAD_TRIP_COUNT - 1):
            assert record_overload_rejection_locked(runtime, now) is None
        deadline = record_overload_rejection_locked(runtime, now)
        assert deadline is not None
        deadlines.append(deadline - now)
        now = deadline  # next burst starts right when the backoff expires

    assert deadlines[:4] == pytest.approx(
        [
            OVERLOAD_BACKOFF_BASE_SECONDS,
            OVERLOAD_BACKOFF_BASE_SECONDS * 2,
            OVERLOAD_BACKOFF_BASE_SECONDS * 4,
            OVERLOAD_BACKOFF_BASE_SECONDS * 8,
        ]
    )
    assert deadlines[-1] == pytest.approx(OVERLOAD_BACKOFF_MAX_SECONDS)


def test_level_saturates_so_sustained_overload_cannot_overflow() -> None:
    assert overload_backoff_seconds(10_000) == OVERLOAD_BACKOFF_MAX_SECONDS
    runtime = RuntimeState(overload_backoff_level=OVERLOAD_MAX_LEVEL, overload_last_trip_at=0.0)
    now = 10.0
    for _ in range(OVERLOAD_TRIP_COUNT - 1):
        record_overload_rejection_locked(runtime, now)
    deadline = record_overload_rejection_locked(runtime, now)
    assert runtime.overload_backoff_level == OVERLOAD_MAX_LEVEL
    assert deadline == pytest.approx(now + OVERLOAD_BACKOFF_MAX_SECONDS)


def test_trip_while_deprioritized_never_shortens_the_deadline() -> None:
    runtime = RuntimeState(overload_backoff_until=5000.0, overload_backoff_level=5, overload_last_trip_at=4000.0)
    for _ in range(OVERLOAD_TRIP_COUNT - 1):
        record_overload_rejection_locked(runtime, 4500.0)
    deadline = record_overload_rejection_locked(runtime, 4500.0)
    # Level 6 => 60 * 2**5 = 1920 s, capped at 600 s => 5100 > 5000.
    assert deadline == pytest.approx(4500.0 + OVERLOAD_BACKOFF_MAX_SECONDS)

    runtime = RuntimeState(overload_backoff_until=9000.0, overload_backoff_level=1, overload_last_trip_at=4000.0)
    for _ in range(OVERLOAD_TRIP_COUNT - 1):
        record_overload_rejection_locked(runtime, 4500.0)
    assert record_overload_rejection_locked(runtime, 4500.0) == 9000.0


def test_level_decays_after_a_quiet_period() -> None:
    runtime = RuntimeState(overload_backoff_level=4, overload_last_trip_at=0.0)
    now = OVERLOAD_LEVEL_DECAY_SECONDS + 1.0
    for _ in range(OVERLOAD_TRIP_COUNT - 1):
        record_overload_rejection_locked(runtime, now)
    deadline = record_overload_rejection_locked(runtime, now)
    assert runtime.overload_backoff_level == 1
    assert deadline == pytest.approx(now + OVERLOAD_BACKOFF_BASE_SECONDS)


def _filter(states: list[AccountState], runtime: dict[str, RuntimeState], now: float) -> list[AccountState]:
    return filter_overload_backoff_candidates(states, runtime, now=now)


def test_filter_returns_the_overload_free_remainder_or_the_pool_itself() -> None:
    now = 1000.0
    runtime = {
        "hot": RuntimeState(overload_backoff_until=now + 30.0),
        "expired": RuntimeState(overload_backoff_until=now - 1.0),
        "clean": RuntimeState(),
    }
    states = [_state("hot"), _state("expired"), _state("clean"), _state("unknown")]

    kept = _filter(states, runtime, now)
    assert [state.account_id for state in kept] == ["expired", "clean", "unknown"]

    only_hot = [_state("hot")]
    assert _filter(only_hot, runtime, now) is only_hot

    all_hot = [_state("hot"), _state("hot2")]
    runtime["hot2"] = RuntimeState(overload_backoff_until=now + 5.0)
    assert _filter(all_hot, runtime, now) is all_hot

    untouched = [_state("clean"), _state("expired")]
    assert _filter(untouched, runtime, now) is untouched


def test_transient_retry_error_code_keeps_overload_codes_from_http_status_failures() -> None:
    def _http_failure(code: str | None) -> SimpleNamespace:
        error: dict[str, object] = {"message": "Our servers are currently overloaded.", "type": "server_error"}
        if code is not None:
            error["code"] = code
        return SimpleNamespace(payload={"error": error}, status_code=500)

    assert _transient_retry_error_code(cast(BaseException, _http_failure("server_is_overloaded"))) == (
        "server_is_overloaded"
    )
    assert _transient_retry_error_code(cast(BaseException, _http_failure("unknown_thing"))) == "server_error"
    assert _transient_retry_error_code(cast(BaseException, _http_failure(None))) == "server_error"
    assert _transient_retry_error_code(RuntimeError("no payload at all")) == "server_error"
    framed = _TransientStreamError("stream_incomplete", {"message": "cut"})
    assert _transient_retry_error_code(framed) == "stream_incomplete"


@pytest.mark.asyncio
async def test_record_upstream_overload_writes_runtime_under_the_account_lock(
    caplog: pytest.LogCaptureFixture, wall_clock: VirtualClock
) -> None:
    clock = wall_clock
    balancer = LoadBalancer(cast(Any, None))
    account = _make_account("acc-overloaded")

    with caplog.at_level(logging.WARNING, logger="app.modules.proxy._load_balancer.overload_backoff"):
        for _ in range(OVERLOAD_TRIP_COUNT - 1):
            await record_upstream_overload(balancer, account)
            clock.advance(1.0)
        assert not overload_backoff_active(balancer._runtime[account.id], clock.time())
        assert "overload backoff engaged" not in caplog.text

        await record_upstream_overload(balancer, account, redact_account_id=True)

    runtime = balancer._runtime[account.id]
    assert runtime.overload_backoff_level == 1
    assert runtime.overload_backoff_until == pytest.approx(clock.time() + OVERLOAD_BACKOFF_BASE_SECONDS)
    assert "Account overload backoff engaged account_id=<redacted> level=1" in caplog.text
    # The generic error counters are untouched: this window is independent of
    # ``record_success`` resetting ``error_count``.
    assert runtime.error_count == 0


@pytest.mark.asyncio
async def test_record_upstream_overload_ignores_balancers_without_a_runtime_map() -> None:
    balancer = SimpleNamespace(record_error=AsyncMock())
    await record_upstream_overload(balancer, _make_account("acc-double"))


@pytest.mark.asyncio
async def test_handle_stream_error_feeds_the_overload_window_for_overload_codes_only(wall_clock: VirtualClock) -> None:
    clock = wall_clock
    balancer = LoadBalancer(cast(Any, None))
    account = _make_account("acc-stream")
    proxy = SimpleNamespace(_load_balancer=balancer)
    # Keep the generic path inert: this test pins the overload hook only.
    balancer.record_error = AsyncMock()  # type: ignore[method-assign]

    classified = await streaming_helpers_module._handle_stream_error(
        proxy,
        account,
        {"message": "Our servers are currently overloaded. Please try again later."},
        "server_is_overloaded",
        None,
    )
    assert classified["failure_class"] == "retryable_transient"
    assert balancer._runtime[account.id].overload_rejections == [clock.time()]
    balancer.record_error.assert_awaited_once()

    await streaming_helpers_module._handle_stream_error(
        proxy,
        account,
        {"message": "upstream hiccup"},
        "server_error",
        None,
    )
    assert balancer._runtime[account.id].overload_rejections == [clock.time()]
    assert balancer.record_error.await_count == 2


@pytest.mark.asyncio
async def test_select_account_skips_backed_off_account_while_a_healthy_sibling_exists(wall_clock: VirtualClock) -> None:
    clock = wall_clock
    hot = _make_account("acc-hot")
    clean = _make_account("acc-clean")
    balancer = LoadBalancer(
        lambda: _repo_factory(_StubAccountsRepository([hot, clean]), _StubUsageRepository({}, {})),
    )
    balancer._runtime[hot.id] = RuntimeState(overload_backoff_until=clock.time() + OVERLOAD_BACKOFF_BASE_SECONDS)

    # Equal weights: 40 draws all landing on ``clean`` is 2**-40 by chance.
    for _ in range(40):
        result = await balancer.select_account()
        assert result.account is not None
        assert result.account.id == clean.id

    clock.advance(OVERLOAD_BACKOFF_BASE_SECONDS + 1.0)
    selected: set[str] = set()
    for _ in range(40):
        result = await balancer.select_account()
        assert result.account is not None
        selected.add(result.account.id)
    assert hot.id in selected


@pytest.mark.asyncio
async def test_select_account_still_uses_backed_off_account_when_every_sibling_is_in_error_backoff(
    wall_clock: VirtualClock,
) -> None:
    clock = wall_clock
    hot = _make_account("acc-hot-only")
    erroring = _make_account("acc-erroring")
    balancer = LoadBalancer(
        lambda: _repo_factory(_StubAccountsRepository([hot, erroring]), _StubUsageRepository({}, {})),
    )
    balancer._runtime[hot.id] = RuntimeState(overload_backoff_until=clock.time() + OVERLOAD_BACKOFF_BASE_SECONDS)
    balancer._runtime[erroring.id] = RuntimeState(error_count=ERROR_BACKOFF_THRESHOLD, last_error_at=clock.time())

    result = await balancer.select_account(lease_kind="stream")

    assert result.error_code is None, result.error_message
    assert result.account is not None
    assert result.account.id == hot.id


@asynccontextmanager
async def _mock_repo_factory():
    yield AsyncMock()


def _sticky_repo(existing_account_id: str | None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_account_id = AsyncMock(return_value=existing_account_id)
    repo.upsert = AsyncMock()
    repo.delete = AsyncMock()
    return repo


async def _select_sticky(balancer: LoadBalancer, states: list[AccountState], repo: AsyncMock):
    account_map = {state.account_id: cast(Account, AsyncMock()) for state in states}
    outcome = await balancer._select_with_stickiness(
        states=states,
        account_map=account_map,
        sticky_key="fresh-or-owned-key",
        sticky_kind=StickySessionKind.PROMPT_CACHE,
        reallocate_sticky=False,
        sticky_max_age_seconds=600,
        prefer_earlier_reset_accounts=False,
        prefer_earlier_reset_window="secondary",
        routing_strategy="usage_weighted",
        sticky_repo=repo,
    )
    return outcome.selection


@pytest.mark.asyncio
async def test_fresh_sticky_binding_avoids_backed_off_account_but_established_owner_is_kept(
    wall_clock: VirtualClock,
) -> None:
    clock = wall_clock
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = RuntimeState(overload_backoff_until=clock.time() + OVERLOAD_BACKOFF_BASE_SECONDS)
    states = [_state("hot"), _state("clean")]

    # A previously unseen key is a fresh upstream admission: bind away from the overloaded account.
    for _ in range(40):
        fresh = await _select_sticky(balancer, [_state("hot"), _state("clean")], _sticky_repo(None))
        assert fresh.account is not None
        assert fresh.account.account_id == "clean"

    # An established owner is warm-session reuse: the overload window never touches it.
    owned = await _select_sticky(balancer, states, _sticky_repo("hot"))
    assert owned.account is not None
    assert owned.account.account_id == "hot"

    # With no overload-free alternative the fresh binding still lands on the backed-off account.
    alone = await _select_sticky(balancer, [_state("hot")], _sticky_repo(None))
    assert alone.account is not None
    assert alone.account.account_id == "hot"


@pytest.mark.asyncio
async def test_fresh_sticky_binding_reports_the_pool_it_selected_from(wall_clock: VirtualClock) -> None:
    """Probe reservation in the sticky run path reuses ``effective_states``; it
    must name the overload-free pool only when that pool produced the pick."""
    clock = wall_clock
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = RuntimeState(overload_backoff_until=clock.time() + OVERLOAD_BACKOFF_BASE_SECONDS)
    hot, clean = _state("hot"), _state("clean")
    account_map = {state.account_id: cast(Account, AsyncMock()) for state in (hot, clean)}

    async def _outcome(states: list[AccountState], existing: str | None):
        return await balancer._select_with_stickiness(
            states=states,
            account_map=account_map,
            sticky_key="key",
            sticky_kind=StickySessionKind.PROMPT_CACHE,
            reallocate_sticky=False,
            sticky_max_age_seconds=600,
            prefer_earlier_reset_accounts=False,
            prefer_earlier_reset_window="secondary",
            routing_strategy="usage_weighted",
            sticky_repo=_sticky_repo(existing),
        )

    filtered = await _outcome([hot, clean], None)
    assert filtered.selection.account is not None and filtered.selection.account.account_id == "clean"
    assert filtered.effective_states is not None
    assert [state.account_id for state in filtered.effective_states] == ["clean"]

    unfiltered = await _outcome([hot], None)
    assert unfiltered.selection.account is not None and unfiltered.selection.account.account_id == "hot"
    assert unfiltered.effective_states is None

    owned = await _outcome([hot, clean], "hot")
    assert owned.selection.account is not None and owned.selection.account.account_id == "hot"
    assert owned.effective_states is None


# --- isolation stage -------------------------------------------------------


def test_isolation_engages_at_the_trip_level_and_holds_for_the_configured_interval() -> None:
    policy = OverloadIsolationPolicy(seconds=1800.0)
    runtime = RuntimeState()
    now = 0.0
    for level in range(1, OVERLOAD_ISOLATION_TRIP_LEVEL + 1):
        for _ in range(OVERLOAD_TRIP_COUNT - 1):
            assert record_overload_rejection_locked(runtime, now, isolation=policy) is None
        deadline = record_overload_rejection_locked(runtime, now, isolation=policy)
        assert deadline is not None
        if level < OVERLOAD_ISOLATION_TRIP_LEVEL:
            assert deadline - now == pytest.approx(overload_backoff_seconds(level))
            assert not overload_isolation_active(runtime, now)
        else:
            assert deadline - now == pytest.approx(1800.0)
            assert overload_isolation_active(runtime, now)
            assert overload_backoff_active(runtime, now)
        now = deadline


def test_isolation_disabled_when_the_interval_is_zero() -> None:
    policy = OverloadIsolationPolicy(seconds=0.0)
    assert not policy.enabled
    runtime = RuntimeState(overload_backoff_level=OVERLOAD_MAX_LEVEL, overload_last_trip_at=0.0)
    for _ in range(OVERLOAD_TRIP_COUNT - 1):
        record_overload_rejection_locked(runtime, 10.0, isolation=policy)
    deadline = record_overload_rejection_locked(runtime, 10.0, isolation=policy)
    assert deadline == pytest.approx(10.0 + OVERLOAD_BACKOFF_MAX_SECONDS)
    assert runtime.overload_isolated_until is None


def test_level_does_not_decay_while_the_account_is_held_out() -> None:
    # Isolated for 1800 s: the quiet period is measured from the deadline, so a
    # trip right after isolation ends keeps the saturated level (re-isolates)
    # instead of dropping back to a 60 s soft backoff.
    policy = OverloadIsolationPolicy(seconds=1800.0)
    runtime = RuntimeState(
        overload_backoff_level=OVERLOAD_ISOLATION_TRIP_LEVEL,
        overload_last_trip_at=0.0,
        overload_backoff_until=1800.0,
        overload_isolated_until=1800.0,
    )
    now = 1800.0 + 60.0
    for _ in range(OVERLOAD_TRIP_COUNT - 1):
        record_overload_rejection_locked(runtime, now, isolation=policy)
    deadline = record_overload_rejection_locked(runtime, now, isolation=policy)
    assert runtime.overload_backoff_level == OVERLOAD_ISOLATION_TRIP_LEVEL + 1
    assert deadline == pytest.approx(now + 1800.0)
    assert overload_isolation_active(runtime, now)

    # A full quiet window after the deadline decays the level as before.
    quiet = RuntimeState(overload_backoff_level=4, overload_last_trip_at=0.0, overload_backoff_until=100.0)
    later = 100.0 + OVERLOAD_LEVEL_DECAY_SECONDS + 1.0
    for _ in range(OVERLOAD_TRIP_COUNT - 1):
        record_overload_rejection_locked(quiet, later, isolation=policy)
    record_overload_rejection_locked(quiet, later, isolation=policy)
    assert quiet.overload_backoff_level == 1


@pytest.mark.asyncio
async def test_record_upstream_overload_logs_isolation_at_the_trip_level(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_LB_PROXY_OVERLOAD_ISOLATION_SECONDS", "900")
    get_settings.cache_clear()
    try:
        clock = VirtualClock(epoch_value=2_000_000_000.0)
        monkeypatch.setattr("time.time", clock.time)
        balancer = LoadBalancer(cast(Any, None))
        account = _make_account("acc-sustained")
        runtime = balancer._runtime.setdefault(account.id, RuntimeState())
        runtime.overload_backoff_level = OVERLOAD_ISOLATION_TRIP_LEVEL - 1
        runtime.overload_last_trip_at = clock.time()
        with caplog.at_level(logging.WARNING, logger="app.modules.proxy._load_balancer.overload_backoff"):
            for _ in range(OVERLOAD_TRIP_COUNT):
                await record_upstream_overload(balancer, account)
        assert (
            "Account overload isolation engaged account_id=acc-sustained level=3 isolation_seconds=900" in caplog.text
        )
        assert overload_isolation_active(runtime, clock.time())
        assert runtime.overload_backoff_until == pytest.approx(clock.time() + 900.0)
    finally:
        get_settings.cache_clear()


def _assert_owner_retained(outcome, owner: str) -> None:
    """The mapping still points at ``owner`` after an isolation reroute.

    Retention is not the same as silence. A TTL-based kind expires on
    ``updated_at``, and the default affinity TTL and the default isolation
    window are both 1800 seconds, so suppressing every write would let the
    retained row die *before* isolation lifts and the next turn would persist
    the substitute as a brand-new owner. Either no mutation at all (durable
    kinds) or a same-owner freshness rewrite (TTL kinds) is correct; a delete
    or a rebind is not.
    """

    if outcome.mutation is None:
        return
    assert outcome.mutation.account_id == owner, outcome.mutation


def _isolated_runtime(now: float, *, seconds: float = 1800.0) -> RuntimeState:
    return RuntimeState(
        overload_backoff_until=now + seconds,
        overload_isolated_until=now + seconds,
        overload_backoff_level=OVERLOAD_ISOLATION_TRIP_LEVEL,
        overload_last_trip_at=now,
    )


def test_sticky_owner_reroute_pool_requires_isolation_and_an_overload_free_sibling() -> None:
    now = 1000.0
    states = [_state("hot"), _state("clean")]
    soft = {"hot": RuntimeState(overload_backoff_until=now + 60.0)}
    assert sticky_owner_isolation_reroute_pool(states, soft, owner_account_id="hot", now=now) is None
    isolated = {"hot": _isolated_runtime(now)}
    pool = sticky_owner_isolation_reroute_pool(states, isolated, owner_account_id="hot", now=now)
    assert pool is not None and [state.account_id for state in pool] == ["clean"]
    # Every sibling isolated too: the owner keeps its session.
    both = {"hot": _isolated_runtime(now), "clean": _isolated_runtime(now)}
    assert sticky_owner_isolation_reroute_pool(states, both, owner_account_id="hot", now=now) is None
    assert sticky_owner_isolation_reroute_pool([_state("hot")], isolated, owner_account_id="hot", now=now) is None
    assert sticky_owner_isolation_reroute_pool(states, None, owner_account_id="hot", now=now) is None
    # Expired isolation releases nothing.
    assert sticky_owner_isolation_reroute_pool(states, isolated, owner_account_id="hot", now=now + 1801.0) is None


def test_the_substitute_seed_is_stable_and_owner_scoped() -> None:
    """The seed stands in for storage the sticky row does not have.

    Two replicas that observe the same overload-free pool must converge on the
    same sibling for a thread without sharing state, the same thread must get
    the same answer on every turn, and distinct threads must spread over the
    siblings instead of herding onto one.
    """

    first = isolation_substitute_seed(sticky_key="thread-1", owner_account_id="owner")
    assert first == isolation_substitute_seed(sticky_key="thread-1", owner_account_id="owner")
    # A thread released under a different owner must not inherit the earlier
    # substitute: the owner is the other half of the pair being replaced.
    assert first != isolation_substitute_seed(sticky_key="thread-1", owner_account_id="other-owner")
    seeds = {isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner") for index in range(50)}
    assert len(seeds) == 50


def test_a_seeded_pick_stays_inside_the_pool_the_selector_would_draw_from() -> None:
    """The seed is spent inside the selector, not on a candidate handed to it.

    Every gate the selector applies is pool-relative -- it takes a draining
    account only when nothing healthier is present, and a ``preserve`` one only
    when no ``normal`` one is -- so a substitute chosen outside and merely
    ratified would slip past all of them.
    """

    draining = _state("draining")
    draining.health_tier = HEALTH_TIER_DRAINING
    preserved = _state("preserved")
    preserved.routing_policy = ROUTING_POLICY_PRESERVE
    pool = [_state("healthy"), draining, preserved]

    for index in range(24):
        result = select_account(
            pool,
            routing_strategy="usage_weighted",
            selection_seed=isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner"),
        )
        assert result.account is not None
        assert result.account.account_id == "healthy", result.account.account_id


async def _select_sticky_outcome(
    balancer: LoadBalancer,
    states: list[AccountState],
    repo: AsyncMock,
    *,
    kind: StickySessionKind = StickySessionKind.PROMPT_CACHE,
    initial_preferred_account_id: str | None = None,
    sticky_key: str = "owned-key",
    reallocate_sticky: bool = False,
    secondary_budget_threshold_pct: float = 100.0,
    preserve_existing_mapping_on_fallback: bool = False,
    preserve_reason_request_local: bool | None = None,
):
    account_map = {state.account_id: cast(Account, AsyncMock()) for state in states}
    return await balancer._select_with_stickiness(
        states=states,
        account_map=account_map,
        sticky_key=sticky_key,
        sticky_kind=kind,
        reallocate_sticky=reallocate_sticky,
        sticky_max_age_seconds=600 if kind == StickySessionKind.PROMPT_CACHE else None,
        secondary_budget_threshold_pct=secondary_budget_threshold_pct,
        preserve_existing_mapping_on_fallback=preserve_existing_mapping_on_fallback,
        # These cases stand in for a capped or retry-excluded owner, which is
        # what request-local preservation means, unless a case says otherwise.
        preserve_reason_request_local=(
            preserve_existing_mapping_on_fallback
            if preserve_reason_request_local is None
            else preserve_reason_request_local
        ),
        prefer_earlier_reset_accounts=False,
        prefer_earlier_reset_window="secondary",
        routing_strategy="usage_weighted",
        sticky_repo=repo,
        initial_preferred_account_id=initial_preferred_account_id,
    )


@pytest.mark.asyncio
async def test_soft_backoff_below_isolation_keeps_the_established_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = RuntimeState(
        overload_backoff_until=clock.time() + OVERLOAD_BACKOFF_MAX_SECONDS,
        overload_backoff_level=OVERLOAD_ISOLATION_TRIP_LEVEL - 1,
    )
    outcome = await _select_sticky_outcome(balancer, [_state("hot"), _state("clean")], _sticky_repo("hot"))
    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id == "hot"
    assert outcome.mutation is None or outcome.mutation.account_id in (None, "hot")


@pytest.mark.asyncio
async def test_isolated_owner_is_kept_when_no_overload_free_sibling_can_be_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    alone = await _select_sticky_outcome(balancer, [_state("hot")], _sticky_repo("hot"))
    assert alone.selection.account is not None and alone.selection.account.account_id == "hot"

    # The only sibling is rate-limited: the strategy rejects the overload-free
    # pool, so the owner is kept rather than failing the request.
    limited = AccountState(
        account_id="limited",
        status=AccountStatus.RATE_LIMITED,
        used_percent=100.0,
        reset_at=clock.time() + 3600.0,
    )
    kept = await _select_sticky_outcome(balancer, [_state("hot"), limited], _sticky_repo("hot"))
    assert kept.selection.account is not None and kept.selection.account.account_id == "hot"


@pytest.mark.asyncio
async def test_expired_isolation_returns_the_owner_to_normal_pinning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time(), seconds=300.0)
    clock.advance(301.0)
    outcome = await _select_sticky_outcome(balancer, [_state("hot"), _state("clean")], _sticky_repo("hot"))
    assert outcome.selection.account is not None and outcome.selection.account.account_id == "hot"


@pytest.mark.asyncio
async def test_backed_off_process_session_preference_is_skipped_for_a_fresh_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = RuntimeState(overload_backoff_until=clock.time() + OVERLOAD_BACKOFF_BASE_SECONDS)

    outcome = await _select_sticky_outcome(
        balancer,
        [_state("hot"), _state("clean")],
        _sticky_repo(None),
        kind=StickySessionKind.CODEX_SESSION,
        initial_preferred_account_id="hot",
    )
    assert outcome.selection.account is not None and outcome.selection.account.account_id == "clean"

    # Without an overload-free alternative the preference is honored as before.
    alone = await _select_sticky_outcome(
        balancer,
        [_state("hot")],
        _sticky_repo(None),
        kind=StickySessionKind.CODEX_SESSION,
        initial_preferred_account_id="hot",
    )
    assert alone.selection.account is not None and alone.selection.account.account_id == "hot"


@pytest.mark.asyncio
async def test_fresh_thread_process_preference_bypass_never_fails_a_request_the_preference_would_serve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Request path (``LoadBalancer.select_account`` with a thread affinity):
    the backed-off process preference is skipped only when the strategy can
    actually select an overload-free sibling; an unselectable sibling
    (cooldown) keeps the preference instead of surfacing its rate-limit error."""
    from app.modules.proxy.affinity import _thread_codex_session_affinity
    from tests.unit.test_load_balancer_concurrency import (
        _StubStickySessionsRepository,
        _usage_row_with_percent,
    )

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    now = int(clock.time())
    preferred = _make_account("acc-preferred")
    sibling = _make_account("acc-sibling")
    affinity = _thread_codex_session_affinity(
        {"session_id": "process", "thread-id": "fresh"}, enabled=True, max_age_seconds=600
    )
    assert affinity is not None
    seed_key = affinity.seed_selection_key
    assert seed_key is not None

    def _balancer(*, sibling_in_cooldown: bool) -> LoadBalancer:
        sticky_repo = _StubStickySessionsRepository()
        sticky_repo.account_ids_by_key = {seed_key: preferred.id}
        usage = _StubUsageRepository(
            {
                preferred.id: _usage_row_with_percent(1, preferred.id, used_percent=96.0, reset_at=now + 3600),
                sibling.id: _usage_row_with_percent(2, sibling.id, used_percent=0.0, reset_at=now + 3600),
            },
            {},
        )
        balancer = LoadBalancer(
            lambda: _repo_factory(_StubAccountsRepository([preferred, sibling]), usage, sticky_repo),
        )
        balancer._runtime[preferred.id] = RuntimeState(overload_backoff_until=clock.time() + 60.0)
        if sibling_in_cooldown:
            balancer._runtime[sibling.id] = RuntimeState(cooldown_until=clock.time() + 3600.0)
        return balancer

    kept = await _balancer(sibling_in_cooldown=True).select_account(
        **affinity.selection_kwargs(), routing_strategy="sequential_drain"
    )
    assert kept.account is not None, kept.error_message
    assert kept.account.id == preferred.id

    moved = await _balancer(sibling_in_cooldown=False).select_account(
        **affinity.selection_kwargs(), routing_strategy="sequential_drain"
    )
    assert moved.account is not None, moved.error_message
    assert moved.account.id == sibling.id


def _isolate(balancer: LoadBalancer, account_id: str) -> None:
    balancer._runtime[account_id] = _isolated_runtime(time.time())


@pytest.mark.asyncio
async def test_isolated_bare_session_owner_is_kept_when_the_only_sibling_is_at_cap_and_spillover_is_off() -> None:
    """Request path: with cap spillover disabled the owner keeps its cap
    exemption and the isolation reroute must not pick a saturated sibling
    that lease admission then rejects (``account_stream_cap``) while the
    isolated owner still had capacity."""
    from tests.unit.test_load_balancer_concurrency import (
        _codex_session_selection_key,
        _make_cap_spillover_balancer,
    )

    balancer, owner, alternate, sticky_repo = _make_cap_spillover_balancer("iso-cap-off")
    assert alternate is not None
    _isolate(balancer, owner.id)
    saturated = [await balancer.acquire_account_lease(alternate.id, kind="stream") for _ in range(8)]
    raw_session = "bare-session-iso-cap-off"
    sticky_repo.account_ids_by_key = {_codex_session_selection_key(raw_session): owner.id}

    selected = await balancer.select_account(
        sticky_key=_codex_session_selection_key(raw_session),
        sticky_kind=StickySessionKind.CODEX_SESSION,
        sticky_source="session_header",
        legacy_sticky_key=raw_session,
        spill_bare_session_on_account_cap=False,
        routing_strategy="usage_weighted",
        lease_kind="stream",
    )
    assert selected.account is not None, selected.error_message
    assert selected.account.id == owner.id
    assert sticky_repo.upserts == []
    for lease in [*saturated, selected.lease]:
        await balancer.release_account_lease(lease)

    # With capacity on the sibling the isolated owner is released for this
    # request only -- the sibling serves the turn, the mapping stays put.
    moved = await balancer.select_account(
        sticky_key=_codex_session_selection_key(raw_session),
        sticky_kind=StickySessionKind.CODEX_SESSION,
        sticky_source="session_header",
        legacy_sticky_key=raw_session,
        spill_bare_session_on_account_cap=False,
        routing_strategy="usage_weighted",
        lease_kind="stream",
    )
    assert moved.account is not None, moved.error_message
    assert moved.account.id == alternate.id
    assert sticky_repo.upserts == []
    await balancer.release_account_lease(moved.lease)


@pytest.mark.asyncio
async def test_isolated_and_capped_bare_session_owner_keeps_its_request_local_spillover() -> None:
    """Request path: cap spillover preserves the mapping (the session returns
    to its owner when the cap clears) and overload isolation is request-local
    for the same reason, so an owner that is both capped and isolated keeps
    its mapping instead of being stranded on the sibling."""
    from tests.unit.test_load_balancer_concurrency import (
        _codex_session_selection_key,
        _make_cap_spillover_balancer,
    )

    balancer, owner, alternate, sticky_repo = _make_cap_spillover_balancer("iso-cap-spill")
    assert alternate is not None
    saturated = [await balancer.acquire_account_lease(owner.id, kind="stream") for _ in range(8)]
    raw_session = "bare-session-iso-cap-spill"
    sticky_repo.account_ids_by_key = {_codex_session_selection_key(raw_session): owner.id}

    def _select():
        return balancer.select_account(
            sticky_key=_codex_session_selection_key(raw_session),
            sticky_kind=StickySessionKind.CODEX_SESSION,
            sticky_source="session_header",
            legacy_sticky_key=raw_session,
            spill_bare_session_on_account_cap=True,
            routing_strategy="usage_weighted",
            lease_kind="stream",
        )

    # Capped but not isolated: request-local spillover, mapping preserved (unchanged behavior).
    spilled = await _select()
    assert spilled.account is not None and spilled.account.id == alternate.id
    assert sticky_repo.upserts == []
    await balancer.release_account_lease(spilled.lease)

    # Capped and isolated: still request-local, still no write.
    _isolate(balancer, owner.id)
    retained = await _select()
    assert retained.account is not None and retained.account.id == alternate.id
    assert sticky_repo.upserts == []
    for lease in [*saturated, retained.lease]:
        await balancer.release_account_lease(lease)


@pytest.mark.asyncio
async def test_budget_pressured_isolated_owner_is_released_with_the_secondary_budget_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-robin would otherwise take the least-recently-selected sibling
    (the equally pressured one), which the next turn's budget reallocation
    would move again; the reroute must honor the secondary-budget filter."""
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["owner"] = _isolated_runtime(clock.time())

    def _st(account_id: str, secondary_used: float, last_selected: float | None) -> AccountState:
        return AccountState(
            account_id=account_id,
            status=AccountStatus.ACTIVE,
            used_percent=10.0,
            secondary_used_percent=secondary_used,
            last_selected_at=last_selected,
            plan_type="plus",
        )

    states = [_st("owner", 85.0, None), _st("pressured", 85.0, None), _st("safe", 20.0, clock.time())]
    account_map = {state.account_id: cast(Account, AsyncMock()) for state in states}
    outcome = await balancer._select_with_stickiness(
        states=states,
        account_map=account_map,
        sticky_key="budget-key",
        sticky_kind=StickySessionKind.PROMPT_CACHE,
        reallocate_sticky=False,
        sticky_max_age_seconds=600,
        budget_threshold_pct=80.0,
        secondary_budget_threshold_pct=80.0,
        prefer_earlier_reset_accounts=False,
        prefer_earlier_reset_window="secondary",
        routing_strategy="round_robin",
        sticky_repo=_sticky_repo("owner"),
    )
    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id == "safe"
    # Request-local: the filter picks the substitute, not a new persisted owner.
    _assert_owner_retained(outcome, "owner")


def _over_budget_on(axis: str, account_id: str) -> AccountState:
    """A sibling the selector rejects as over budget on exactly one axis.

    The default sticky budget threshold is 95%, and the selector reads priority
    usage in preference to raw usage and checks the secondary window too, so
    each of these is invisible to a filter that only compares ``used_percent``.
    """
    state = AccountState(account_id=account_id, status=AccountStatus.ACTIVE, used_percent=0.0)
    if axis == "primary":
        state.used_percent = 99.0
    elif axis == "priority":
        state.priority_used_percent = 99.0
    else:
        state.secondary_used_percent = 99.0
        state.priority_secondary_used_percent = 99.0
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("axis", ["primary", "priority", "secondary"])
async def test_a_substitute_never_crosses_the_budget_threshold(monkeypatch: pytest.MonkeyPatch, axis: str) -> None:
    """The selector's budget filter is pool-relative.

    ``_select_account_preferring_budget_safe`` accepts an over-budget account
    only when no safe one is visible, so validating a deterministic preference
    on the candidate *alone* hides that filter: the thread could be pinned to an
    exhausted sibling while a safe one sat in the same pool. The scoping that
    prevents it has to mirror the selector on *every* axis it reads -- priority
    and secondary usage included -- or it readmits what it meant to exclude.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())
    # The owner is itself over budget, so the reroute turns the secondary
    # threshold on: the substitute is filtered exactly as the pool pick is.
    owner = _over_budget_on("primary", "hot")
    states = [owner, _state("safe"), _over_budget_on(axis, "pressured")]

    for index in range(24):
        outcome = await _select_sticky_outcome(
            balancer,
            states,
            _sticky_repo("hot"),
            sticky_key=f"thread-{index}",
            # The secondary window has its own threshold; lowering it keeps the
            # fixture's usage figures inside the 0-100 range a real account
            # reports while still putting the sibling over the line.
            secondary_budget_threshold_pct=90.0,
        )
        assert outcome.selection.account is not None
        assert outcome.selection.account.account_id == "safe", f"{axis}-exhausted sibling served thread-{index}"


@pytest.mark.asyncio
async def test_a_retained_ttl_mapping_is_kept_fresh_rather_than_left_to_expire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retention must not mean silence.

    A TTL kind expires on ``updated_at``. The default affinity TTL and the
    default isolation window are both 1800 s, so suppressing every write would
    let the retained row die before isolation lifts and the next turn would
    persist the substitute as a brand-new owner -- the accumulation this change
    removes, arriving through the back door.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    outcome = await _select_sticky_outcome(
        balancer,
        [_state("hot"), _state("clean")],
        _sticky_repo("hot"),
        kind=StickySessionKind.PROMPT_CACHE,
    )

    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id == "clean"
    assert outcome.mutation is not None, "a TTL row must be refreshed, not left to expire"
    assert outcome.mutation.account_id == "hot", "the refresh must not rebind"


def test_a_seeded_pick_honors_the_strategy_s_own_narrowing() -> None:
    """The seed replaces the draw, not the strategy.

    Every weighted strategy narrows before it draws -- to the lowest planner
    cost, and under ``prefer_earlier_reset`` to the soonest reset bucket. A seed
    spent before those filters would hold a thread on an account the strategy
    had already ruled out, for as long as the isolation lasts.
    """

    now = 2_000_000_000.0
    costs = {"cheap": RoutingCost(total=1.0), "expensive": RoutingCost(total=99.0)}

    for index in range(24):
        seed = isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner")
        for strategy in _SEEDED_STRATEGIES:
            by_cost = select_account(
                [_state("cheap"), _state("expensive")],
                now,
                routing_strategy=strategy,
                routing_costs=costs,
                selection_seed=seed,
            )
            assert by_cost.account is not None
            assert by_cost.account.account_id == "cheap", f"{strategy} took the higher planner cost"

            if strategy not in _RESET_PREFERRING_STRATEGIES:
                # ``round_robin`` orders by cost and recency and
                # ``relative_availability`` by availability; neither consults
                # the reset bucket, seeded or not.
                continue
            soon, later = _state("soon"), _state("later")
            soon.secondary_reset_at = int(now + 3600.0)
            later.secondary_reset_at = int(now + 30 * 86400.0)
            by_reset = select_account(
                [soon, later],
                now,
                routing_strategy=strategy,
                prefer_earlier_reset=True,
                selection_seed=seed,
            )
            assert by_reset.account is not None
            assert by_reset.account.account_id == "soon", f"{strategy} took the later reset bucket"


def test_a_seeded_pick_trades_weight_magnitude_for_not_moving() -> None:
    """The deliberate trade on the seeded path, pinned so it stays deliberate.

    The draw's weights are live -- a usage refresh, an elapsed reset or an
    error-rate update moves them with nothing about eligibility changing -- so a
    pick weighted by their magnitude puts every retained thread one refresh away
    from flipping. Inside the isolation window the seeded pick therefore spreads
    uniformly over the accounts the draw had already accepted, while ordinary
    traffic keeps the full weighted draw and with it the pool's capacity
    balance.
    """

    now = 2_000_000_000.0
    large, small = _state("large"), _state("small")
    large.capacity_credits = 1000.0
    large.secondary_used_percent = 1.0
    small.capacity_credits = 1000.0
    small.secondary_used_percent = 97.0

    seeded = []
    for index in range(400):
        seed = isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner")
        result = select_account([large, small], now, routing_strategy="capacity_weighted", selection_seed=seed)
        assert result.account is not None
        seeded.append(result.account.account_id)

    # Uniform over the eligible pool -- not proportional to the 33x capacity gap.
    assert 0.35 < seeded.count("large") / len(seeded) < 0.65, seeded.count("large") / len(seeded)

    # The unseeded draw is untouched, so the fleet still follows capacity.
    unseeded = []
    for _ in range(400):
        result = select_account([large, small], now, routing_strategy="capacity_weighted")
        assert result.account is not None
        unseeded.append(result.account.account_id)
    assert unseeded.count("large") / len(unseeded) > 0.9, unseeded.count("large") / len(unseeded)

    # And each thread's own answer is still fixed.
    seed = isolation_substitute_seed(sticky_key="thread-7", owner_account_id="owner")
    repeated = set()
    for _ in range(8):
        again = select_account([large, small], now, routing_strategy="capacity_weighted", selection_seed=seed)
        assert again.account is not None
        repeated.add(again.account.account_id)
    assert len(repeated) == 1


def test_a_seeded_pick_does_not_follow_a_reshuffled_ranking() -> None:
    """Rank cuts move for reasons that are not about the thread.

    ``relative_availability`` admits its top ``k`` by live availability, so a
    sibling can stay well within reach and still drop out of that slice the
    moment another account's usage refreshes. A retained thread following that
    reordering would leave a substitute that never became ineligible.
    """

    now = 2_000_000_000.0
    pool = []
    for index in range(10):
        state = _state(f"sibling-{index}")
        state.capacity_credits = 1000.0
        state.secondary_used_percent = 10.0
        pool.append(state)

    flipped = []
    for index in range(100):
        for state in pool:
            state.secondary_used_percent = 10.0
        seed = isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner")
        first = select_account(pool, now, routing_strategy="relative_availability", selection_seed=seed)
        assert first.account is not None
        # Every *other* account refreshes to a better position, reshuffling the
        # ranking without the substitute becoming ineligible.
        for state in pool:
            if state.account_id != first.account.account_id:
                state.secondary_used_percent = 2.0
        second = select_account(pool, now, routing_strategy="relative_availability", selection_seed=seed)
        assert second.account is not None
        if second.account.account_id != first.account.account_id:
            flipped.append((first.account.account_id, second.account.account_id))

    assert not flipped, f"{len(flipped)}/100 threads followed the reshuffle: {flipped[:5]}"


def test_a_seeded_pick_still_spreads_threads_over_an_equally_scored_pool() -> None:
    """Stability per thread must not become herding across threads.

    ``relative_availability`` admits only its top ``k``, and a membership rule
    keyed globally rather than per thread would hand every retained
    conversation the same five accounts while the rest of an equally scored
    pool never served a turn.
    """

    now = 2_000_000_000.0
    pool = []
    for index in range(12):
        state = _state(f"sibling-{index}")
        state.capacity_credits = 1000.0
        state.secondary_used_percent = 10.0
        pool.append(state)

    picks = set()
    for index in range(200):
        seed = isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner")
        result = select_account(pool, now, routing_strategy="relative_availability", selection_seed=seed)
        assert result.account is not None
        picks.add(result.account.account_id)

    # Default top-k is 5; a globally keyed membership rule would cap this there.
    assert len(picks) > 5, sorted(picks)


@pytest.mark.parametrize("strategy", ["capacity_weighted", "relative_availability"])
def test_a_seeded_pick_survives_its_own_consumption(strategy: RoutingStrategy) -> None:
    """Weighting must not reintroduce the rotation it was added alongside.

    The weights move as the pool is used, and the retained thread is one of the
    things using it. Scoring raw credits leaves every thread one admission away
    from flipping -- whichever ones happen to hold a narrow lead over their
    runner-up -- so a conversation's own turns walk it off its substitute
    inside a single isolation window: exactly the fan-out being removed. The
    score is taken from the weight's coarse bucket instead, so consumption on
    this scale cannot move it for *any* thread.
    """

    now = 2_000_000_000.0

    def _pool() -> list[AccountState]:
        pool = []
        for index in range(5):
            state = _state(f"sibling-{index}")
            state.capacity_credits = 1000.0
            # ~900 remaining: comfortably inside one bucket, so the drop below
            # is real consumption rather than a genuine change in capacity tier.
            state.secondary_used_percent = 10.0
            pool.append(state)
        return pool

    flipped = []
    for index in range(200):
        pool = _pool()
        seed = isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner")
        first = select_account(pool, now, routing_strategy=strategy, selection_seed=seed)
        assert first.account is not None
        # What serving a stretch of turns costs the account that served them.
        first.account.secondary_used_percent = 40.0
        second = select_account(pool, now, routing_strategy=strategy, selection_seed=seed)
        assert second.account is not None
        if second.account.account_id != first.account.account_id:
            flipped.append((first.account.account_id, second.account.account_id))

    assert not flipped, f"{len(flipped)}/200 threads left their substitute after serving: {flipped[:5]}"


def test_a_seeded_pick_leaves_fill_first_s_ranking_alone() -> None:
    """``fill_first`` drains an account before opening the next.

    Its ranking is already stable across admissions, so a seed has nothing to
    add there and would only scatter threads onto fresh accounts -- the
    opposite of what the strategy is for.
    """

    now = 2_000_000_000.0
    draining, fresh = _state("draining"), _state("fresh")
    draining.used_percent = 90.0
    fresh.used_percent = 0.0

    for index in range(24):
        seed = isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner")
        result = select_account([draining, fresh], now, routing_strategy="fill_first", selection_seed=seed)
        assert result.account is not None
        assert result.account.account_id == "draining", "fill-first opened a fresh account"


def test_a_seeded_pick_skips_an_account_the_draw_could_never_have_returned() -> None:
    """Weight zero means "spent", and a weighted draw can never return it while
    a positive-weight sibling exists. Hashing over the raw pool could."""

    now = 2_000_000_000.0
    spent = _state("spent")
    spent.capacity_credits = 1000.0
    spent.secondary_used_percent = 100.0
    live = _state("live")
    live.capacity_credits = 1000.0
    live.secondary_used_percent = 0.0

    for index in range(24):
        seed = isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner")
        for strategy in ("capacity_weighted", "relative_availability"):
            result = select_account([spent, live], now, routing_strategy=strategy, selection_seed=seed)
            assert result.account is not None
            assert result.account.account_id == "live", f"{strategy} routed to a spent account"


def test_a_seeded_pick_does_not_move_as_its_own_turns_are_admitted() -> None:
    """Stability has to survive the side effects of being used.

    ``relative_availability`` admits only its top ``k`` candidates, and exact
    ties there were broken by *recency* -- so each admitted turn advanced the
    winner's ``last_selected_at`` and ejected it from the next turn's top-k,
    cycling a thread through its siblings while nothing about the pool changed.
    """

    now = 2_000_000_000.0
    pool = [_state(f"sibling-{index}") for index in range(8)]
    for state in pool:
        state.capacity_credits = 1000.0
        state.secondary_used_percent = 10.0
    seed = isolation_substitute_seed(sticky_key="thread", owner_account_id="owner")

    picks = []
    for turn in range(24):
        result = select_account(
            pool,
            now + turn,
            routing_strategy="relative_availability",
            selection_seed=seed,
        )
        assert result.account is not None
        picks.append(result.account.account_id)
        # What admission does to the winner, and what used to eject it.
        result.account.last_selected_at = now + turn

    assert len(set(picks)) == 1, picks


def test_relative_availability_seeded_top_k_spreads_and_survives_live_weight_changes() -> None:
    """A seeded relative-availability caller must not share one global top-k.

    The owner-isolation substitute is picked on every retained turn. Its
    membership therefore has to be stable for this thread, while distinct
    thread seeds still spread across the eligible siblings.
    """

    now = 2_000_000_000.0

    def _pool() -> list[AccountState]:
        pool = [_state(f"sibling-{index}") for index in range(8)]
        for state in pool:
            state.capacity_credits = 1000.0
            state.secondary_used_percent = 10.0
            state.secondary_reset_at = int(now + 3600.0)
        return pool

    spread = set()
    for index in range(40):
        seed = isolation_substitute_seed(sticky_key=f"thread-{index}", owner_account_id="owner")
        first_pool = _pool()
        first = select_account(
            first_pool,
            now,
            routing_strategy="relative_availability",
            relative_availability_top_k=2,
            selection_seed=seed,
        )
        assert first.account is not None
        spread.add(first.account.account_id)

    assert len(spread) > 2, spread

    seed = isolation_substitute_seed(sticky_key="thread-stable", owner_account_id="owner")
    pool = _pool()
    first = select_account(
        pool,
        now,
        routing_strategy="relative_availability",
        relative_availability_top_k=2,
        selection_seed=seed,
    )
    assert first.account is not None
    # Degrade the substitute, but not past the relative-availability floor: the
    # pick must survive live weight changes, while an account that falls *far*
    # behind the best is no longer eligible at all -- the same kind of bound as
    # the budget threshold, which a seeded pick also cannot cross.
    first.account.secondary_used_percent = 40.0
    second = select_account(
        pool,
        now + 60.0,
        routing_strategy="relative_availability",
        relative_availability_top_k=2,
        selection_seed=seed,
    )
    assert second.account is not None
    assert second.account.account_id == first.account.account_id


def test_a_seeded_pick_is_stable_even_when_every_sibling_is_spent() -> None:
    """The exhausted-pool fallback is where rotation hurts most.

    It orders by usage and ends in ``last_selected_at``, so when every
    candidate is equally spent -- exactly when it runs -- being chosen is what
    loses you the next turn.
    """

    now = 2_000_000_000.0
    pool = [_state(f"spent-{index}") for index in range(6)]
    for state in pool:
        state.capacity_credits = 1000.0
        state.secondary_used_percent = 100.0
    seed = isolation_substitute_seed(sticky_key="thread", owner_account_id="owner")

    for strategy in ("capacity_weighted", "relative_availability"):
        picks = []
        for turn in range(24):
            result = select_account(pool, now + turn, routing_strategy=strategy, selection_seed=seed)
            assert result.account is not None
            picks.append(result.account.account_id)
            result.account.last_selected_at = now + turn
        assert len(set(picks)) == 1, f"{strategy}: {picks}"


@pytest.mark.asyncio
async def test_a_seeded_pick_does_not_carry_recovery_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recovery probe is the one admission that is *meant* to move.

    The due probe is whichever probing account went quiet longest, so admitting
    one advances its clock and hands the next turn to a different sibling --
    precisely the rotation a retained thread is being protected from. Probes
    ride on every other request instead, so nothing here starves recovery.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())
    # Probe due-ness is measured against the wall clock inside ``select_account``
    # (it takes no ``now``), so these timestamps are real-time, not virtual.
    probing = []
    for index in range(3):
        state = _state(f"probing-{index}")
        state.health_tier = HEALTH_TIER_PROBING
        state.last_selected_at = time.time() - 600.0 - index
        probing.append(state)
    states = [_state("hot"), *probing]

    picks = []
    for _ in range(24):
        outcome = await _select_sticky_outcome(balancer, states, _sticky_repo("hot"))
        assert outcome.selection.account is not None
        picks.append(outcome.selection.account.account_id)
        for state in states:
            if state.account_id == picks[-1]:
                # What admission does to the winner, and what used to hand the
                # next turn to one of its siblings.
                state.last_selected_at = time.time()

    assert len(set(picks)) == 1, picks


@pytest.mark.asyncio
async def test_an_owner_that_is_gone_is_rebound_rather_than_refreshed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retention is for owners that come back.

    A paused or deactivated owner is not "isolated, will recover" -- it is
    gone, so the mapping is released on this turn rather than held (and kept
    refreshed) for the isolation window.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())
    gone = _state("hot")
    gone.status = AccountStatus.DEACTIVATED

    outcome = await _select_sticky_outcome(
        balancer,
        [gone, _state("clean")],
        _sticky_repo("hot"),
    )

    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id == "clean"
    assert outcome.mutation is not None
    assert outcome.mutation.account_id != "hot", "a deactivated owner must be released, not refreshed"


@pytest.mark.asyncio
async def test_a_release_that_did_not_happen_is_not_counted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The counter measures releases, not intentions.

    An isolated owner past recovering is logged as rebound only once a
    different account has actually been selected -- the request may instead
    fail outright, and a release that never happened must not appear in the
    metric the rollout is judged by.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())
    gone = _state("hot")
    gone.status = AccountStatus.DEACTIVATED

    caplog.set_level(logging.INFO, logger="app.modules.proxy.load_balancer")
    outcome = await _select_sticky_outcome(balancer, [gone], _sticky_repo("hot"))

    assert outcome.selection.account is None
    messages = [record.getMessage() for record in caplog.records]
    assert not [message for message in messages if "sticky_owner_overload_isolation_reroute" in message], messages


@pytest.mark.asyncio
async def test_a_permanent_isolation_release_is_logged_as_rebound(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Both halves of what isolation does to a conversation are counted."""

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())
    gone = _state("hot")
    gone.status = AccountStatus.PAUSED

    outcome = await _select_sticky_outcome(balancer, [gone, _state("clean")], _sticky_repo("hot"))

    assert outcome.isolation_release is not None
    assert outcome.isolation_release[0] == "rebound"


@pytest.mark.asyncio
async def test_a_capped_isolated_owner_is_kept_fresh_even_though_it_never_reached_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retention has a second door.

    An owner removed by a cap or by this request's exclusion list never reaches
    the selection states, so the isolation branch sees no pinned state and the
    mapping is kept by the fallback-preservation path instead. That path wrote
    nothing, so on a TTL kind the retained row expired mid-episode -- the
    default TTL and the default isolation window are both 1800 seconds -- and
    the next turn persisted the substitute as a brand-new owner.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    outcome = await _select_sticky_outcome(
        balancer,
        # "hot" is absent: capped out of the pool before selection ran.
        [_state("clean"), _state("spare")],
        _sticky_repo("hot"),
        preserve_existing_mapping_on_fallback=True,
    )

    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id != "hot"
    assert outcome.mutation is not None, "the retained row must be refreshed, not left to expire"
    assert outcome.mutation.account_id == "hot", "the refresh must not rebind"


@pytest.mark.asyncio
async def test_an_explicit_reallocation_still_retires_an_isolated_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``reallocate_sticky`` is an instruction to retire the mapping.

    It outranks retention, exactly as it already does on the TTL-bounded
    branch.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    outcome = await _select_sticky_outcome(
        balancer,
        [_state("hot"), _state("clean")],
        _sticky_repo("hot"),
        reallocate_sticky=True,
    )

    assert outcome.selection.account is not None
    assert outcome.mutation is not None
    assert outcome.mutation.account_id != "hot", "reallocation must not be swallowed by retention"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [StickySessionKind.PROMPT_CACHE, StickySessionKind.STICKY_THREAD, StickySessionKind.CODEX_SESSION],
)
async def test_isolated_soft_sticky_owner_is_served_by_a_substitute_without_rebinding(
    monkeypatch: pytest.MonkeyPatch,
    kind: StickySessionKind,
) -> None:
    """The release is request-local: the sibling serves the turn and the
    sticky row keeps pointing at the isolated owner, so the thread returns
    home when isolation lifts instead of gaining a permanent new owner."""
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    outcome = await _select_sticky_outcome(balancer, [_state("hot"), _state("clean")], _sticky_repo("hot"), kind=kind)
    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id == "clean"
    # No delete and no rebind: the mapping survives the isolation episode.
    _assert_owner_retained(outcome, "hot")
    assert outcome.effective_states is not None
    assert [state.account_id for state in outcome.effective_states] == ["clean"]


@pytest.mark.asyncio
async def test_legacy_sticky_thread_isolation_retain_outranks_its_reallocate_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``sticky_threads_enabled`` uses STICKY_THREAD with reallocate=True.

    That is the normal legacy sticky-thread policy, not a caller command to
    retire an overload-isolated warm owner.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    outcome = await _select_sticky_outcome(
        balancer,
        [_state("hot"), _state("clean")],
        _sticky_repo("hot"),
        kind=StickySessionKind.STICKY_THREAD,
        reallocate_sticky=True,
    )

    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id == "clean"
    _assert_owner_retained(outcome, "hot")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [StickySessionKind.PROMPT_CACHE, StickySessionKind.STICKY_THREAD, StickySessionKind.CODEX_SESSION],
)
async def test_isolated_soft_sticky_owner_keeps_one_substitute_across_turns(
    monkeypatch: pytest.MonkeyPatch, kind: StickySessionKind
) -> None:
    """Substitute stability is the correctness condition for request-local
    release: the pick is repeated every turn, so a weighted-random draw would
    bounce the thread across siblings and be worse than the single rebind it
    replaces."""
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())
    states = [_state("hot"), _state("clean-a"), _state("clean-b"), _state("clean-c"), _state("clean-d")]

    chosen = set()
    for _ in range(24):
        outcome = await _select_sticky_outcome(balancer, states, _sticky_repo("hot"), kind=kind)
        assert outcome.selection.account is not None
        _assert_owner_retained(outcome, "hot")
        chosen.add(outcome.selection.account.account_id)
    assert len(chosen) == 1, chosen
    assert "hot" not in chosen

    # Distinct threads are spread across the siblings rather than herded onto
    # a single "best" account, so retention does not concentrate load.
    spread = set()
    for index in range(40):
        outcome = await _select_sticky_outcome(
            balancer,
            states,
            _sticky_repo("hot"),
            kind=kind,
            sticky_key=f"thread-{index}",
        )
        assert outcome.selection.account is not None
        spread.add(outcome.selection.account.account_id)
    assert len(spread) > 1, spread


@pytest.mark.asyncio
async def test_isolated_owner_that_is_no_longer_recoverable_is_released_on_the_next_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Availability bound: retention only ever applies to an owner that can
    come back. A PAUSED/DEACTIVATED owner is abandoned on the very next turn
    rather than held for the isolation window."""
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["dead"] = _isolated_runtime(clock.time())
    dead = AccountState(account_id="dead", status=AccountStatus.DEACTIVATED, used_percent=0.0)

    outcome = await _select_sticky_outcome(balancer, [dead, _state("clean")], _sticky_repo("dead"))
    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id == "clean"
    # Rebound, not retained: the mapping is released within one turn.
    assert outcome.mutation is not None and outcome.mutation.account_id == "clean"


@pytest.mark.asyncio
async def test_explicit_reallocation_still_retires_an_isolated_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``reallocate_sticky`` is an explicit instruction to retire the mapping.
    Isolation retention must not silently override it."""
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    outcome = await _select_sticky_outcome(
        balancer,
        [_state("hot"), _state("clean")],
        _sticky_repo("hot"),
        reallocate_sticky=True,
    )
    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id == "clean"
    assert outcome.mutation is not None and outcome.mutation.account_id == "clean"
    assert outcome.isolation_release is not None
    assert outcome.isolation_release[0] == "rebound"


@pytest.mark.asyncio
async def test_isolated_hard_sticky_owner_is_not_released_or_rebound() -> None:
    """Hard continuity owners keep their existing semantics. A hard Codex
    session mapping is an ownership constraint, not a locality hint, so
    overload isolation must neither serve it elsewhere nor touch its row."""
    from tests.unit.test_load_balancer_concurrency import _make_cap_spillover_balancer

    balancer, owner, alternate, sticky_repo = _make_cap_spillover_balancer("iso-hard-owner")
    assert alternate is not None
    _isolate(balancer, owner.id)
    sticky_repo.account_ids_by_key = {"hard-session": owner.id}

    selected = await balancer.select_account(
        sticky_key="hard-session",
        sticky_kind=StickySessionKind.CODEX_SESSION,
        routing_strategy="usage_weighted",
        lease_kind="stream",
    )
    assert selected.account is not None, selected.error_message
    assert selected.account.id == owner.id
    assert sticky_repo.upserts == []
    assert sticky_repo.deleted == []
    await balancer.release_account_lease(selected.lease)


@pytest.mark.asyncio
async def test_request_local_isolation_release_is_logged_as_retained(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The diagnostic is what makes the accounts-per-conversation change
    attributable: it says the turn went to a sibling without adding an owner."""
    clock = VirtualClock(epoch_value=2_000_000_000.0)
    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    caplog.set_level(logging.INFO, logger="app.modules.proxy.load_balancer")
    outcome = await _select_sticky_outcome(balancer, [_state("hot"), _state("clean")], _sticky_repo("hot"))

    _assert_owner_retained(outcome, "hot")
    # The diagnostic is carried, not logged: selection can still lose the
    # candidate to a concurrent lease, so the caller emits it once admission
    # has succeeded (covered end-to-end in test_load_balancer_concurrency).
    assert outcome.isolation_release is not None
    mapping, candidates = outcome.isolation_release
    assert mapping == "retained"
    assert candidates == 1


@pytest.mark.asyncio
async def test_an_ambiguously_owned_pinned_mapping_is_kept_but_not_extended(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ambiguity is a reason not to rebind, not a reason to hold on harder.

    The owner still keeps its row -- that is what preserving it means -- but a
    turn served elsewhere must not extend the TTL of a mapping the request
    could not confirm, and it is not an isolation release to count.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    caplog.set_level(logging.INFO, logger="app.modules.proxy.load_balancer")
    outcome = await _select_sticky_outcome(
        balancer,
        [_state("hot"), _state("clean")],
        _sticky_repo("hot"),
        preserve_existing_mapping_on_fallback=True,
        preserve_reason_request_local=False,
    )

    assert outcome.selection.account is not None
    assert outcome.selection.account.account_id == "clean"
    assert outcome.mutation is None, "the row is kept as-is, neither rebound nor refreshed"
    messages = [record.getMessage() for record in caplog.records]
    assert not [message for message in messages if "sticky_owner_overload_isolation_reroute" in message], messages


@pytest.mark.asyncio
async def test_ordinary_spillover_keeps_its_load_proportional_draw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stability is bought for a reason, and only where there is one.

    An owner that is merely capped or retry-excluded is coming back this turn
    or the next on a healthy pool. Seeding that spillover would trade the
    pool's load-proportional draw -- and its recovery probes -- for a stability
    nothing is asking for.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    # No isolation anywhere: this is ordinary request-local spillover.
    states = [_state(f"sibling-{index}") for index in range(6)]

    picks = set()
    for index, state in enumerate(states):
        state.used_percent = float(index)
    for _ in range(40):
        outcome = await _select_sticky_outcome(
            balancer,
            states,
            _sticky_repo("hot"),
            preserve_existing_mapping_on_fallback=True,
        )
        assert outcome.selection.account is not None
        picks.add(outcome.selection.account.account_id)
        for state in states:
            if state.account_id == outcome.selection.account.account_id:
                state.used_percent = (state.used_percent or 0.0) + 3.0

    # A load-proportional draw visits most of the pool over 40 turns; a seeded
    # one visits a single account (and at most one more, once the first crosses
    # the budget threshold).
    assert len(picks) >= 4, f"spillover stopped following usage: {sorted(picks)}"


@pytest.mark.asyncio
async def test_an_ambiguously_owned_mapping_is_not_treated_as_a_warm_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not every preserved mapping is a warm owner waiting out isolation.

    ``require_unambiguous_account`` preserves a mapping because the
    conversation's ownership is ambiguous, and that owner may be outside this
    request's routable or security scope. Refreshing it would pin the thread to
    an account that cannot serve it, turn after turn.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    outcome = await _select_sticky_outcome(
        balancer,
        [_state("clean"), _state("spare")],
        _sticky_repo("hot"),
        preserve_existing_mapping_on_fallback=True,
        preserve_reason_request_local=False,
    )

    assert outcome.selection.account is not None
    assert outcome.mutation is None, "an ambiguously owned mapping must not be refreshed onto its owner"


@pytest.mark.asyncio
async def test_an_off_pool_ambiguously_owned_mapping_does_not_emit_isolation_rebound(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Preserving an ambiguous row is not the same as rebinding an owner."""

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    caplog.set_level(logging.INFO, logger="app.modules.proxy.load_balancer")
    outcome = await _select_sticky_outcome(
        balancer,
        [_state("clean"), _state("spare")],
        _sticky_repo("hot"),
        preserve_existing_mapping_on_fallback=True,
        preserve_reason_request_local=False,
    )

    assert outcome.selection.account is not None
    assert outcome.mutation is None
    assert "sticky_owner_overload_isolation_reroute" not in caplog.text


@pytest.mark.asyncio
async def test_a_capped_isolated_owner_s_release_is_logged_as_retained_too(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The counter must not undercount the second retention door.

    An owner removed by a cap or an exclusion before selection ran is released
    by the fallback-preservation path, which used to log only the generic
    spillover line -- so exactly the releases this change is measured by went
    missing from the isolation metric.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["hot"] = _isolated_runtime(clock.time())

    caplog.set_level(logging.INFO, logger="app.modules.proxy.load_balancer")
    outcome = await _select_sticky_outcome(
        balancer,
        [_state("clean"), _state("spare")],
        _sticky_repo("hot"),
        preserve_existing_mapping_on_fallback=True,
    )

    assert outcome.selection.account is not None
    assert outcome.isolation_release is not None
    assert outcome.isolation_release[0] == "retained"


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_status", [AccountStatus.ACTIVE, AccountStatus.RATE_LIMITED])
async def test_off_pool_budget_pressured_isolated_owner_uses_the_secondary_budget_filter(
    monkeypatch: pytest.MonkeyPatch,
    owner_status: AccountStatus,
) -> None:
    """The cap/exclusion path must carry the same budget filter as pinned retention.

    Including for a rate-limited owner: the pinned branch skips the filter for
    that status because such an owner takes the grace-retry path instead of
    budget reallocation, but an owner that never reached selection has no grace
    path to take, so skipping it would just hand the substitute to a sibling the
    budget rule excludes.
    """

    clock = VirtualClock(epoch_value=2_000_000_000.0)

    monkeypatch.setattr("time.time", clock.time)
    balancer = LoadBalancer(_mock_repo_factory)
    balancer._runtime["owner"] = _isolated_runtime(clock.time())

    def _st(account_id: str, secondary_used: float, last_selected: float | None) -> AccountState:
        return AccountState(
            account_id=account_id,
            status=AccountStatus.ACTIVE,
            used_percent=10.0,
            secondary_used_percent=secondary_used,
            last_selected_at=last_selected,
            plan_type="plus",
        )

    owner = _st("owner", 85.0, None)
    owner.status = owner_status
    pressured = _st("pressured", 85.0, None)
    safe = _st("safe", 20.0, clock.time())
    states = [pressured, safe]
    account_map = {state.account_id: cast(Account, AsyncMock()) for state in states}
    # Several threads: the substitute is seeded per sticky key, so a single key
    # can land on the safe sibling by luck even when the filter is missing.
    for index in range(12):
        outcome = await _off_pool_budget_outcome(balancer, states, account_map, f"budget-key-{index}", owner, safe)
        assert outcome.selection.account is not None
        assert outcome.selection.account.account_id == "safe", outcome.selection.account.account_id
        assert outcome.mutation is not None
        _assert_owner_retained(outcome, "owner")


async def _off_pool_budget_outcome(
    balancer: LoadBalancer,
    states: list[AccountState],
    account_map: dict[str, Account],
    sticky_key: str,
    owner: AccountState,
    safe: AccountState,
):
    return await balancer._select_with_stickiness(
        states=states,
        account_map=account_map,
        sticky_key=sticky_key,
        sticky_kind=StickySessionKind.PROMPT_CACHE,
        reallocate_sticky=False,
        sticky_max_age_seconds=600,
        budget_threshold_pct=80.0,
        secondary_budget_threshold_pct=80.0,
        prefer_earlier_reset_accounts=False,
        prefer_earlier_reset_window="secondary",
        routing_strategy="round_robin",
        sticky_repo=_sticky_repo("owner"),
        preserve_existing_mapping_on_fallback=True,
        preserve_reason_request_local=True,
        usage_exhaustion_states=[owner, *states],
    )


_SEEDED_STRATEGIES = ("capacity_weighted", "relative_availability", "usage_weighted", "round_robin")

_RESET_PREFERRING_STRATEGIES = ("capacity_weighted", "usage_weighted")
