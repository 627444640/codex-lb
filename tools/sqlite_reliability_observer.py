#!/usr/bin/env python3
"""Bounded read-only operational snapshots; request logs are not a capacity benchmark."""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path


def percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def snapshot(database: Path, backend_log: Path, window_hours: int) -> dict:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=window_hours)).replace(tzinfo=None)
    end = now.replace(tzinfo=None)
    try:
        wal_bytes = Path(str(database) + "-wal").stat().st_size
    except FileNotFoundError:
        # Checkpoints may remove WAL between samples; absence is a size of zero,
        # not evidence that there has been no write traffic.
        wal_bytes = 0
    result = {
        "observed_at": now.isoformat(),
        "window_hours": window_hours,
        "database_bytes": database.stat().st_size,
        "wal_bytes": wal_bytes,
        "write_wait_measurement": (
            "slow process-local writer acquisition only; available when an explicit wait log is present"
        ),
        "all_background_queues": "not_measured",
        "model_requests_generated": 0,
    }
    opened = time.monotonic()
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.set_progress_handler(lambda: int(time.monotonic() - opened > 5), 10000)
        connection.execute("BEGIN")
        result["journal_mode"] = connection.execute("PRAGMA journal_mode").fetchone()[0]
        result["request_status_counts"] = dict(
            connection.execute(
                "SELECT status,COUNT(*) FROM request_logs WHERE requested_at>=? AND requested_at<? GROUP BY status",
                (str(start), str(end)),
            ).fetchall()
        )
        result["error_counts"] = dict(
            connection.execute(
                "SELECT COALESCE(error_code,'unknown'),COUNT(*) FROM request_logs "
                "WHERE requested_at>=? AND requested_at<? AND status='error' GROUP BY error_code",
                (str(start), str(end)),
            ).fetchall()
        )
        result["request_kind_counts"] = dict(
            connection.execute(
                "SELECT COALESCE(request_kind,'unknown'),COUNT(*) FROM request_logs "
                "WHERE requested_at>=? AND requested_at<? GROUP BY request_kind",
                (str(start), str(end)),
            ).fetchall()
        )
        rows = connection.execute(
            "SELECT latency_ms,latency_first_output_ms FROM request_logs "
            "WHERE requested_at>=? AND requested_at<? AND status='success' AND request_kind='normal'",
            (str(start), str(end)),
        ).fetchall()
        total = [r[0] for r in rows if isinstance(r[0], int) and r[0] >= 0]
        first = [r[1] for r in rows if isinstance(r[1], int) and r[1] >= 0]
        result["successful_normal_requests"] = {
            "count": len(rows),
            "latency_samples": len(total),
            "first_output_samples": len(first),
            "latency_p50_ms": percentile(total, 0.5),
            "latency_p95_ms": percentile(total, 0.95),
            "first_output_p50_ms": percentile(first, 0.5),
            "first_output_p95_ms": percentile(first, 0.95),
        }
        row = connection.execute("SELECT hourly_folded_through FROM account_usage_rollup_state LIMIT 1").fetchone()
        watermark = row[0] if row else None
        result["hourly_rollup_watermark_utc"] = watermark
        result["hourly_rollup_tail_rows"] = (
            connection.execute(
                "SELECT COUNT(*) FROM request_logs WHERE requested_at>=?",
                (watermark,),
            ).fetchone()[0]
            if watermark
            else None
        )
        connection.rollback()
    result["metadata_query_elapsed_ms"] = round((time.monotonic() - opened) * 1000, 2)
    markers = Counter()
    waits = []
    observed_lines = 0
    # The supervisor prefix is local UTC+8 in this deployment. The nested
    # timestamp is the application's UTC timestamp and is preferred here.
    utc_pattern = re.compile(r"\b(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)Z\b")
    if backend_log.exists():
        with backend_log.open(errors="replace") as stream:
            for line in stream:
                match = utc_pattern.search(line)
                if not match:
                    continue
                stamp = datetime.fromisoformat(match.group(1))
                if not start <= stamp < end:
                    continue
                observed_lines += 1
                for marker in [
                    "database is locked",
                    "database table is locked",
                    "SQLITE_BUSY",
                    "sqlite_long_write_transaction",
                    "sqlite_writer_wait",
                    "account_stream_cap",
                    "bridge_queue_full",
                ]:
                    if marker in line:
                        markers[marker] += 1
                if "sqlite_writer_wait" in line:
                    measured = re.search(r"wait_seconds=([0-9.]+)", line)
                    if measured:
                        waits.append(float(measured.group(1)))
    result["log_observation"] = {
        "lines_in_window": observed_lines,
        "marker_event_counts": dict(markers),
        "explicit_writer_wait_samples": len(waits),
        "max_observed_writer_wait_seconds": max(waits) if waits else None,
        "counting_note": "log events may repeat one request; missing markers do not prove zero waiting",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backend-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=5)
    args = parser.parse_args()
    if not 1 <= args.samples <= 12 or not 1 <= args.window_hours <= 168 or not 0 <= args.interval_seconds <= 30:
        parser.error("use 1-12 samples, a 1-168 hour window and a 0-30 second interval")
    observations = []
    for index in range(args.samples):
        observations.append(snapshot(args.database, args.backend_log, args.window_hours))
        if index + 1 < args.samples:
            time.sleep(args.interval_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump({"observations": observations, "continuous_monitor_installed": False}, output, indent=2)
        output.write("\n")
    print(json.dumps({"output": str(args.output), "samples": len(observations), "model_requests_generated": 0}))


if __name__ == "__main__":
    main()
