from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.sqlite_reliability_observer import snapshot

pytestmark = pytest.mark.unit


def test_observer_separates_request_kinds_missing_timing_and_wait_evidence(tmp_path: Path) -> None:
    database = tmp_path / "store.db"
    log = tmp_path / "backend.log"
    stamp = datetime.now(timezone.utc) - timedelta(seconds=3)
    value = str(stamp.replace(tzinfo=None))
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript("""
            CREATE TABLE request_logs(requested_at TEXT, status TEXT, error_code TEXT,
                request_kind TEXT, latency_ms INTEGER, latency_first_output_ms INTEGER);
            CREATE TABLE account_usage_rollup_state(hourly_folded_through TEXT);
        """)
        connection.executemany(
            "INSERT INTO request_logs VALUES (?,?,?,?,?,?)",
            [
                (value, "success", None, "normal", 1000, 200),
                (value, "success", None, "normal", 3000, None),
                (value, "success", None, "prewarm", 999999, 999999),
                (value, "error", "server_is_overloaded", "normal", 5000, None),
            ],
        )
        connection.execute("INSERT INTO account_usage_rollup_state VALUES (?)", (value,))
        connection.commit()
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    log.write_text(
        stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        + " sqlite_writer_wait wait_seconds=0.125000 outcome=acquired queue_depth=2 scope=process_local\n"
    )
    observed = snapshot(database, log, 24)
    normal = observed["successful_normal_requests"]
    assert normal["count"] == 2 and normal["first_output_samples"] == 1
    assert normal["latency_p95_ms"] == 3000 and normal["first_output_p95_ms"] == 200
    assert observed["error_counts"] == {"server_is_overloaded": 1}
    assert observed["log_observation"]["max_observed_writer_wait_seconds"] == 0.125
    assert observed["all_background_queues"] == "not_measured"
    assert observed["hourly_rollup_tail_rows"] == 4
    assert observed["model_requests_generated"] == 0
    assert hashlib.sha256(database.read_bytes()).hexdigest() == digest
    log.write_text("")
    missing = snapshot(database, log, 24)["log_observation"]
    assert missing["explicit_writer_wait_samples"] == 0
    assert missing["max_observed_writer_wait_seconds"] is None
