from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.clients.codex_version import CodexVersionCache
from app.core.usage import metadata_scheduler as module
from app.core.usage import pricing_catalog as catalog
from app.core.usage.pricing import ModelPrice, get_pricing_for_model


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(catalog, "_prices", None)
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    cache = CodexVersionCache()
    monkeypatch.setattr(cache, "_fetch_latest_version", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "get_codex_version_cache", lambda: cache)
    return tmp_path


async def test_refresh_persists_and_offline_restart_restores(setup, monkeypatch):
    monkeypatch.setattr(module, "fetch_catalogs", AsyncMock(return_value={"gpt-test": ModelPrice(3, 9)}))
    first = module.MetadataRefreshScheduler()
    await first._refresh()
    assert get_pricing_for_model("gpt-test") == ("gpt-test", ModelPrice(3, 9))
    assert json.loads((setup / "pricing-cache.json").read_text())["models"]["gpt-test"]["input_per_1m"] == 3
    monkeypatch.setattr(catalog, "_prices", None)
    monkeypatch.setattr(module, "fetch_catalogs", AsyncMock(side_effect=ValueError("offline")))
    second = module.MetadataRefreshScheduler()
    monkeypatch.setattr(second, "_run_loop", AsyncMock())
    await second.start()
    await second._refresh()
    assert get_pricing_for_model("gpt-test") == ("gpt-test", ModelPrice(3, 9))
    await second.stop()
    assert second._task is None


async def test_stop_cancels_owned_fetch_and_no_follower_backfill(setup, monkeypatch):
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def fetch():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(module, "fetch_catalogs", fetch)
    leader = SimpleNamespace(run_if_leader=AsyncMock(return_value=False))
    monkeypatch.setattr(module, "get_leader_election", lambda: leader)
    scheduler = module.MetadataRefreshScheduler()
    await scheduler.start()
    await asyncio.wait_for(entered.wait(), timeout=1)
    await scheduler.stop()
    assert cancelled.is_set()
    leader.run_if_leader.assert_not_called()


async def test_newer_bundle_beats_old_disk_cache(setup, monkeypatch):
    stale = json.loads(catalog.encode_snapshot({"gpt-6-astra": ModelPrice(1, 2)}))
    stale["updated_at"] = "2000-01-01T00:00:00+00:00"
    (setup / "pricing-cache.json").write_text(json.dumps(stale))
    scheduler = module.MetadataRefreshScheduler()
    monkeypatch.setattr(scheduler, "_run_loop", AsyncMock())
    await scheduler.start()
    bundled = catalog.decode_snapshot(json.loads(catalog.BUNDLE_PATH.read_text()))
    assert get_pricing_for_model("gpt-6-astra") == ("gpt-6-astra", bundled["gpt-6-astra"])
    await scheduler.stop()


async def test_follower_refreshes_prices_without_running_backfill(setup, monkeypatch):
    refreshed = asyncio.Event()
    finished = asyncio.Event()

    async def fetch():
        refreshed.set()
        return {"gpt-test": ModelPrice(3, 9)}

    async def run_if_leader(callback):
        finished.set()
        return False

    monkeypatch.setattr(module, "fetch_catalogs", fetch)
    monkeypatch.setattr(module, "get_leader_election", lambda: SimpleNamespace(run_if_leader=run_if_leader))
    scheduler = module.MetadataRefreshScheduler()
    backfill = AsyncMock()
    monkeypatch.setattr(scheduler, "_backfill", backfill)
    await scheduler.start()
    await asyncio.wait_for(finished.wait(), timeout=1)
    await scheduler.stop()
    assert refreshed.is_set()
    assert get_pricing_for_model("gpt-test") == ("gpt-test", ModelPrice(3, 9))
    backfill.assert_not_awaited()


async def test_compatible_partial_refresh_does_not_restart_backfill_cursor(setup, monkeypatch):
    catalog.install_prices({"gpt-test": ModelPrice(10, 50, 1, flex_input_per_1m=5, flex_output_per_1m=25)})
    monkeypatch.setattr(module, "fetch_catalogs", AsyncMock(return_value={"gpt-test": ModelPrice(10, 50, 1)}))
    scheduler = module.MetadataRefreshScheduler(_cursor=123)
    await scheduler._refresh()
    assert scheduler._cursor == 123


@pytest.mark.parametrize("failed_operation", ["refresh", "backfill"])
async def test_unexpected_failure_backs_off_only_the_failed_operation(setup, monkeypatch, failed_operation):
    current = 0.0
    ticks = iter([5.0, 300.0])
    scheduler = module.MetadataRefreshScheduler()
    fetch = AsyncMock(return_value={"gpt-test": ModelPrice(3, 9)})
    backfill = AsyncMock(return_value=True)
    if failed_operation == "refresh":
        fetch.side_effect = RuntimeError("unexpected catalog failure")
    else:
        backfill.side_effect = RuntimeError("database unavailable")

    async def run_if_leader(callback):
        return await callback()

    async def advance_tick(awaitable, *, timeout):
        nonlocal current
        awaitable.close()
        try:
            current = next(ticks)
        except StopIteration:
            scheduler._stop.set()
        raise TimeoutError

    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: current))
    monkeypatch.setattr(module, "fetch_catalogs", fetch)
    monkeypatch.setattr(scheduler, "_backfill", backfill)
    monkeypatch.setattr(module, "get_leader_election", lambda: SimpleNamespace(run_if_leader=run_if_leader))
    monkeypatch.setattr(module.asyncio, "wait_for", advance_tick)
    await scheduler._run_loop()
    assert fetch.await_count == (2 if failed_operation == "refresh" else 1)
    assert backfill.await_count == (2 if failed_operation == "backfill" else 3)


async def test_refresh_and_restart_preserve_effective_price_version_and_accounting_fields(setup, monkeypatch):
    from dataclasses import replace

    from app.core.usage.pricing import get_pricing_version

    resolved = get_pricing_for_model("gpt-6-astra")
    assert resolved is not None
    updated = replace(resolved[1], input_per_1m=11.0, cache_write_multiplier=1.5)
    monkeypatch.setattr(module, "fetch_catalogs", AsyncMock(return_value={"gpt-6-astra": updated}))
    scheduler = module.MetadataRefreshScheduler()
    await scheduler._refresh()
    version = get_pricing_version("gpt-6-astra")
    assert version == get_pricing_version(price=updated)
    monkeypatch.setattr(catalog, "_prices", None)
    restarted = module.MetadataRefreshScheduler()
    monkeypatch.setattr(restarted, "_run_loop", AsyncMock())
    await restarted.start()
    assert get_pricing_for_model("gpt-6-astra") == ("gpt-6-astra", updated)
    assert get_pricing_version("gpt-6-astra") == version
    await restarted.stop()


async def test_new_cache_cannot_reintroduce_known_unpriced_model(setup, monkeypatch):
    snapshot = json.loads(catalog.encode_snapshot({"gpt-valid": ModelPrice(1, 2)}))
    snapshot["updated_at"] = "2099-01-01T00:00:00+00:00"
    snapshot["models"]["gpt-5.3-codex-spark"] = {"input_per_1m": 1.75, "output_per_1m": 14}
    (setup / "pricing-cache.json").write_text(json.dumps(snapshot))
    scheduler = module.MetadataRefreshScheduler()
    monkeypatch.setattr(scheduler, "_run_loop", AsyncMock())
    await scheduler.start()
    assert get_pricing_for_model("gpt-5.3-codex-spark") is None
    assert get_pricing_for_model("gpt-valid") == ("gpt-valid", ModelPrice(1, 2))
    await scheduler.stop()


async def test_base_only_refresh_keeps_long_context_price_and_does_not_restart_backfill(setup, monkeypatch):
    from app.core.usage.pricing import UsageTokens, calculate_cost_from_usage, get_pricing_version

    resolved = get_pricing_for_model("gpt-5.5")
    assert resolved is not None
    before = resolved[1]
    version = get_pricing_version("gpt-5.5")
    monkeypatch.setattr(module, "fetch_catalogs", AsyncMock(return_value={"gpt-5.5": ModelPrice(5, 30, 0.5)}))
    scheduler = module.MetadataRefreshScheduler(_cursor=123)
    await scheduler._refresh()
    assert scheduler._cursor == 123
    assert get_pricing_version("gpt-5.5") == version
    persisted = catalog.decode_snapshot(json.loads((setup / "pricing-cache.json").read_text()))
    assert persisted["gpt-5.5"] == before
    assert calculate_cost_from_usage(UsageTokens(300000, 1000), persisted["gpt-5.5"]) == pytest.approx(3.045)
