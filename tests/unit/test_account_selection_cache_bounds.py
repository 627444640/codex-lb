from __future__ import annotations

import asyncio
import gc
import weakref

import pytest

import app.modules.proxy.account_cache as cache_module
from app.db.models import Account
from app.modules.proxy.account_cache import AccountSelectionCache
from app.modules.proxy.load_balancer import SelectionInputs

pytestmark = pytest.mark.unit


def _snapshot(account_id: str) -> SelectionInputs:
    return SelectionInputs(accounts=[Account(id=account_id)], latest_primary={}, latest_secondary={}, latest_monthly={})


def _key(model: str) -> tuple[str, None, None, str, None]:
    return model, None, None, "", None


async def test_default_capacity_bounds_retained_account_snapshots() -> None:
    cache = AccountSelectionCache(ttl_seconds=60)
    accounts: list[weakref.ReferenceType[Account]] = []
    for index in range(1024):
        snapshot = _snapshot(str(index))
        accounts.append(weakref.ref(snapshot.accounts[0]))
        await cache.set(snapshot, _key(str(index)))
    del snapshot
    gc.collect()

    assert sum(account() is not None for account in accounts) <= 256
    assert await cache.get(_key("0")) is None
    latest = await cache.get(_key("1023"))
    assert latest is not None and latest.accounts[0].id == "1023"


async def test_disabled_cache_does_not_retain_a_snapshot() -> None:
    cache = AccountSelectionCache(ttl_seconds=0)
    snapshot = _snapshot("disabled")
    account = weakref.ref(snapshot.accounts[0])
    await cache.set(snapshot)
    del snapshot
    gc.collect()

    assert await cache.get() is None
    assert account() is None


async def test_expired_read_releases_its_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now)
    cache = AccountSelectionCache(ttl_seconds=5)
    snapshot = _snapshot("expired")
    account = weakref.ref(snapshot.accounts[0])
    await cache.set(snapshot)
    del snapshot
    now = 105.0

    assert await cache.get() is None
    gc.collect()
    assert account() is None


async def test_write_reclaims_expired_scopes_that_are_never_read_again(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now)
    cache = AccountSelectionCache(ttl_seconds=5)
    snapshot = _snapshot("old")
    account = weakref.ref(snapshot.accounts[0])
    await cache.set(snapshot, _key("old-model"))
    del snapshot
    now = 106.0

    await cache.set(_snapshot("new"), _key("new-model"))
    gc.collect()
    assert account() is None
    current = await cache.get(_key("new-model"))
    assert current is not None and current.accounts[0].id == "new"


async def test_replacing_a_scope_preserves_expiry_order(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now)
    cache = AccountSelectionCache(ttl_seconds=5, max_entries=2)
    await cache.set(_snapshot("first"), _key("one"))
    now = 101.0
    second = _snapshot("second")
    account = weakref.ref(second.accounts[0])
    await cache.set(second, _key("two"))
    del second
    now = 104.0
    await cache.set(_snapshot("replacement"), _key("one"))
    now = 107.0
    await cache.set(_snapshot("third"), _key("three"))

    gc.collect()
    assert account() is None
    replacement = await cache.get(_key("one"))
    assert replacement is not None and replacement.accounts[0].id == "replacement"
    assert await cache.get(_key("two")) is None


async def test_eviction_does_not_invalidate_or_defeat_generation_fencing(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_poller_access() -> None:
        pytest.fail("capacity eviction must not propagate an invalidation")

    with monkeypatch.context() as scoped:
        scoped.setattr(cache_module, "get_cache_invalidation_poller", unexpected_poller_access)
        cache = AccountSelectionCache(ttl_seconds=60, max_entries=1)
        generation = cache.generation
        await cache.set(_snapshot("one"), _key("one"), generation=generation)
        await cache.set(_snapshot("two"), _key("two"), generation=generation)
        assert cache.generation == generation
        assert await cache.get(_key("one")) is None

        cache.invalidate(propagate=False)
        await cache.set(_snapshot("stale"), _key("stale"), generation=generation)
        assert await cache.get(_key("stale")) is None
        await cache.set(_snapshot("current"), _key("current"), generation=cache.generation)
        assert await cache.get(_key("current")) is not None


@pytest.mark.parametrize("max_entries", [0, -1])
def test_invalid_capacity_fails_fast(max_entries: int) -> None:
    with pytest.raises(ValueError, match="max_entries"):
        AccountSelectionCache(ttl_seconds=5, max_entries=max_entries)


async def test_distinct_load_scopes_progress_independently() -> None:
    cache = AccountSelectionCache(ttl_seconds=60)
    first_entered, second_entered, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def load(model: str, entered: asyncio.Event) -> None:
        async with cache.load_scope(_key(model)):
            entered.set()
            await finish.wait()

    first = asyncio.create_task(load("first", first_entered))
    await first_entered.wait()
    second = asyncio.create_task(load("second", second_entered))
    try:
        await asyncio.wait_for(second_entered.wait(), timeout=3)
    finally:
        finish.set()
        await asyncio.gather(first, second)
    assert not cache._load_gates


async def test_cancelled_load_waiter_does_not_abandon_the_owner() -> None:
    cache = AccountSelectionCache(ttl_seconds=60)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def load() -> None:
        async with cache.load_scope(_key("shared")):
            entered.set()
            await finish.wait()

    owner = asyncio.create_task(load())
    await entered.wait()
    waiter = asyncio.create_task(load())
    try:
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert not owner.done()
        assert len(cache._load_gates) == 1
    finally:
        finish.set()
        await owner
    assert not cache._load_gates


async def test_invalidation_fences_owner_and_waiter_reloads_current_snapshot() -> None:
    cache = AccountSelectionCache(ttl_seconds=60)
    entered, finish = asyncio.Event(), asyncio.Event()
    key = _key("generation")

    async def old_load() -> None:
        async with cache.load_scope(key):
            generation = cache.generation
            entered.set()
            await finish.wait()
            await cache.set(_snapshot("stale"), key, generation=generation)

    async def fresh_load() -> None:
        async with cache.load_scope(key):
            assert await cache.get(key) is None
            await cache.set(_snapshot("current"), key, generation=cache.generation)

    owner = asyncio.create_task(old_load())
    await entered.wait()
    waiter = asyncio.create_task(fresh_load())
    cache.invalidate(propagate=False)
    finish.set()
    await asyncio.gather(owner, waiter)
    result = await cache.get(key)
    assert result is not None and result.accounts[0].id == "current"
    assert not cache._load_gates


async def test_disabled_cache_allocates_no_load_coordination() -> None:
    cache = AccountSelectionCache(ttl_seconds=0)
    async with cache.load_scope(_key("disabled")):
        assert not cache._load_gates
