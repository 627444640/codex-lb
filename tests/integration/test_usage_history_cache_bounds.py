from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from app.core.crypto import TokenEncryptor
from app.core.retention.job import _prune_usage_history
from app.core.utils.time import naive_utc_to_epoch
from app.db.models import Account, AccountStatus
from app.db.session import SessionLocal
from app.modules.accounts.repository import AccountsRepository
from app.modules.dashboard import service as dashboard_service
from app.modules.usage import repository as usage

pytestmark = pytest.mark.integration
_START = datetime(2026, 1, 1)


@pytest.fixture(autouse=True)
def clear_history_cache():
    usage._clear_bulk_history_since_sqlite_cache()
    yield
    usage._clear_bulk_history_since_sqlite_cache()


@pytest.fixture
def history_db(tmp_path):
    path = str(tmp_path / "history.db")
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "create table usage_history (id integer primary key, account_id text, used_percent real, "
            "recorded_at text, reset_at real, window_minutes integer, window text)"
        )
        conn.executemany(
            "insert into usage_history values (?, 'acc', ?, ?, 1000, 60, 'primary')",
            [(index + 1, index * 10.0, str(_START + timedelta(minutes=index))) for index in range(3)],
        )
    return path


def _read(path: str, since: datetime = _START, account: str = "acc"):
    return usage._bulk_history_since_sqlite(path, [account], "primary", since)


def test_history_cache_discards_old_rows_and_wider_query_reloads(history_db, monkeypatch):
    assert len(_read(history_db)["acc"]) == 3
    cutoff = _START + timedelta(minutes=2)
    queried_cutoffs = []
    query = usage._query_bulk_history_metadata_sqlite

    def record_query(conn, accounts, window, since, **kwargs):
        queried_cutoffs.append(since)
        return query(conn, accounts, window, since, **kwargs)

    monkeypatch.setattr(usage, "_query_bulk_history_metadata_sqlite", record_query)
    assert [row.id for row in _read(history_db, cutoff)["acc"]] == [3]
    cached = next(iter(usage._BULK_HISTORY_SQLITE_CACHE.values()))
    assert cached.since == cutoff
    assert cached.metadata.row_count == 1
    assert [row.id for row in cached.rows_by_account["acc"]] == [3]
    assert queried_cutoffs == [cutoff]
    assert [row.id for row in _read(history_db)["acc"]] == [1, 2, 3]


def test_cache_expiry_entry_budget_and_row_budget_preserve_complete_results(history_db, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(usage, "monotonic", lambda: now[0])
    monkeypatch.setattr(usage, "_BULK_HISTORY_SQLITE_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(usage, "_BULK_HISTORY_SQLITE_CACHE_MAX_ROWS", 3)
    assert len(_read(history_db)["acc"]) == 3
    original = next(iter(usage._BULK_HISTORY_SQLITE_CACHE.values()))
    now[0] = 31.0
    assert len(_read(history_db)["acc"]) == 3
    assert next(iter(usage._BULK_HISTORY_SQLITE_CACHE.values())) is not original
    for account in ("empty1", "empty2", "empty3"):
        assert _read(history_db, account=account) == {}
        assert len(usage._BULK_HISTORY_SQLITE_CACHE) <= 2
    monkeypatch.setattr(usage, "_BULK_HISTORY_SQLITE_CACHE_MAX_ROWS", 2)
    assert len(_read(history_db)["acc"]) == 3
    assert all(key[1] != ("acc",) for key in usage._BULK_HISTORY_SQLITE_CACHE)
    assert sum(entry.metadata.row_count for entry in usage._BULK_HISTORY_SQLITE_CACHE.values()) <= 2


def test_invalidation_and_unrelated_reads_do_not_wait_for_hashing(history_db, monkeypatch):
    _read(history_db)
    entered = threading.Event()
    release = threading.Event()
    query = usage._query_bulk_history_metadata_sqlite

    def blocked_metadata(*args, **kwargs):
        metadata = query(*args, **kwargs)
        entered.set()
        assert release.wait(3)
        return metadata

    monkeypatch.setattr(usage, "_query_bulk_history_metadata_sqlite", blocked_metadata)
    with ThreadPoolExecutor(max_workers=3) as executor:
        slow = executor.submit(_read, history_db)
        try:
            assert entered.wait(2)
            clear = executor.submit(usage._clear_bulk_history_since_sqlite_cache)
            clear.result(timeout=0.5)
            other = executor.submit(_read, history_db, _START, "unrelated")
            assert other.result(timeout=0.5) == {}
        finally:
            release.set()
        assert len(slow.result(timeout=2)["acc"]) == 3
    assert all(key[1] != ("acc",) for key in usage._BULK_HISTORY_SQLITE_CACHE)


def test_metadata_and_tail_share_one_database_snapshot(history_db, monkeypatch):
    _read(history_db)
    query = usage._query_bulk_history_metadata_sqlite

    def modify_after_verification(*args, **kwargs):
        metadata = query(*args, **kwargs)
        with sqlite3.connect(history_db) as conn:
            conn.execute("update usage_history set used_percent = 99 where id = 1")
            conn.execute(
                "insert or ignore into usage_history values (4, 'acc', 40, '2026-01-01 00:03:00', 1000, 60, 'primary')"
            )
        return metadata

    monkeypatch.setattr(usage, "_query_bulk_history_metadata_sqlite", modify_after_verification)
    snapshot = _read(history_db)["acc"]
    assert [row.id for row in snapshot] == [1, 2, 3]
    assert snapshot[0].used_percent == 0.0
    monkeypatch.setattr(usage, "_query_bulk_history_metadata_sqlite", query)
    corrected = _read(history_db)["acc"]
    assert [row.id for row in corrected] == [1, 2, 3, 4]
    assert corrected[0].used_percent == 99.0


@pytest.mark.asyncio
async def test_dashboard_projection_moves_cache_window_and_retention_invalidates(async_client, monkeypatch):
    now = [_START + timedelta(minutes=60)]
    monkeypatch.setattr(dashboard_service, "utcnow", lambda: now[0])
    encryptor = TokenEncryptor()
    async with SessionLocal() as session:
        await AccountsRepository(session).upsert(
            Account(
                id="cache-projection",
                email="cache@example.invalid",
                plan_type="plus",
                status=AccountStatus.ACTIVE,
                access_token_encrypted=encryptor.encrypt("test-access"),
                refresh_token_encrypted=encryptor.encrypt("test-refresh"),
                id_token_encrypted=encryptor.encrypt("test-id"),
                last_refresh=now[0],
            )
        )
        repo = usage.UsageRepository(session)
        for minute in (10, 30, 50):
            await repo.add_entry(
                "cache-projection",
                float(minute),
                window="primary",
                window_minutes=60,
                recorded_at=_START + timedelta(minutes=minute),
                reset_at=int(naive_utc_to_epoch(_START + timedelta(hours=2))),
            )
    first = await async_client.get("/api/dashboard/projections")
    assert first.status_code == 200
    assert first.json()["depletionPrimary"] is not None
    assert sum(entry.metadata.row_count for entry in usage._BULK_HISTORY_SQLITE_CACHE.values()) == 3
    now[0] += timedelta(minutes=20)
    second = await async_client.get("/api/dashboard/projections")
    assert second.status_code == 200
    assert second.json()["depletionPrimary"] is not None
    assert sum(entry.metadata.row_count for entry in usage._BULK_HISTORY_SQLITE_CACHE.values()) == 2
    # Real retention path must clear published entries; the newest row survives.
    assert await _prune_usage_history(_START + timedelta(minutes=40)) == 2
    assert usage._BULK_HISTORY_SQLITE_CACHE == {}
    third = await async_client.get("/api/dashboard/projections")
    assert third.status_code == 200
    assert sum(entry.metadata.row_count for entry in usage._BULK_HISTORY_SQLITE_CACHE.values()) == 1
