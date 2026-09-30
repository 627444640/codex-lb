from __future__ import annotations

import math
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import httpx

from .config import Settings


def epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


def sql_time(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def percentile(values, q):
    values = sorted(v for v in values if isinstance(v, (int, float)) and math.isfinite(v) and v >= 0)
    return round(values[max(0, math.ceil(len(values) * q) - 1)], 1) if values else None


def normalize_windows(rows, now, stale_seconds):
    """Use actual durations; never project a past reset into an invented full quota."""
    result = {}
    labels = {300: "primary", 10080: "secondary", 43200: "monthly"}
    aliases = {None: "primary", "5h": "primary", "7d": "secondary", "30d": "monthly"}
    for row in rows:
        if row["window_minutes"] == 0:
            continue  # Upstream placeholder, not an actual zero-length quota window.
        key = labels.get(row["window_minutes"])
        if key is None:
            key = aliases.get(row["window"], row["window"])
        if key not in {"primary", "secondary", "monthly"}:
            continue
        at = epoch(row["recorded_at"])
        reset = epoch(row["reset_at"])
        used = row["used_percent"]
        valid = isinstance(used, (float, int)) and math.isfinite(used) and 0 <= used <= 100
        fresh = bool(at is not None and -30 <= now - at <= stale_seconds and (reset is None or reset > now))
        value = {
            "remaining_percent": round(100 - used, 2) if valid and fresh else None,
            "recorded_at": at,
            "reset_at": reset,
            "fresh": fresh and valid,
        }
        if key not in result or (at or 0) > (result[key]["recorded_at"] or 0):
            result[key] = value
    # A later monthly-only sample supersedes leftover 5h/7d history.
    if "monthly" in result and all(
        (result["monthly"]["recorded_at"] or 0) > (v["recorded_at"] or 0) + 5
        for k, v in result.items()
        if k != "monthly"
    ):
        return {"monthly": result["monthly"]}
    if "monthly" in result and any(
        (v["recorded_at"] or 0) > (result["monthly"]["recorded_at"] or 0) + 5
        for k, v in result.items()
        if k != "monthly"
    ):
        result.pop("monthly")
    return result


def pool_summary(accounts, usage, now, settings):
    states = Counter(a["status"] for a in accounts)
    grouped = defaultdict(list)
    for a in accounts:
        grouped[a["plan_type"].lower()].append(a)
    plans = []
    ready = unknown = exhausted = 0
    all_remaining = []
    for plan, members in sorted(grouped.items()):
        active = [a for a in members if a["status"] == "active"]
        summaries = []
        for a in active:
            windows = normalize_windows(usage.get(a["id"], []), now, settings.stale_seconds)
            if set(windows) == {"monthly"}:
                expected = {"monthly"}
            elif set(windows) == {"secondary"} and any(
                r["window"] in {"primary", "5h", None} and r["window_minutes"] == 10080 for r in usage.get(a["id"], [])
            ):
                expected = {"secondary"}
            elif plan == "free":
                expected = set(windows) or {"monthly"}
            else:
                expected = {"primary", "secondary"}
            values = [windows.get(k, {}).get("remaining_percent") for k in expected]
            is_empty = any(v is not None and v <= 0 for v in values)
            is_unknown = any(v is None for v in values)
            if is_empty:
                exhausted += 1
            elif is_unknown:
                unknown += 1
            else:
                ready += 1
            all_remaining.extend(v for v in values if v is not None)
            summaries.append((windows, expected))
        window_summaries = []
        keys = set().union(*(e for _, e in summaries)) if summaries else set()
        for key in ("primary", "secondary", "monthly"):
            if key not in keys:
                continue
            relevant = [w.get(key, {}) for w, e in summaries if key in e]
            values = [w["remaining_percent"] for w in relevant if w.get("remaining_percent") is not None]
            resets = [w["reset_at"] for w in relevant if w.get("fresh") and w.get("reset_at")]
            ats = [w["recorded_at"] for w in relevant if w.get("recorded_at")]
            window_summaries.append(
                {
                    "key": key,
                    "remaining_percent": round(sum(values) / len(values), 2) if values else None,
                    "known": len(values),
                    "expected": len(relevant),
                    "next_reset_at": min(resets) if resets else None,
                    "oldest_sample_at": min(ats) if ats else None,
                }
            )
        plans.append({"plan": plan, "total": len(members), "active": len(active), "windows": window_summaries})
    return {
        "total": len(accounts),
        "active": states["active"],
        "quota_ready": ready,
        "quota_unknown": unknown,
        "quota_exhausted": exhausted,
        "states": dict(states),
        "plans": plans,
        "lowest_remaining_percent": min(all_remaining) if all_remaining else None,
    }


def read_source(settings: Settings, now: float):
    deadline = time.monotonic() + 4
    conn = sqlite3.connect(settings.source_db.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 2000)
    try:
        conn.execute("BEGIN")
        account_cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)")}
        where = "WHERE delete_requested_at IS NULL" if "delete_requested_at" in account_cols else ""
        accounts = conn.execute(f"SELECT id, plan_type, status FROM accounts {where} LIMIT 10001").fetchall()
        if len(accounts) > 10000:
            raise ValueError("Account limit exceeded")
        usage = {}
        for a in accounts:
            rows = []
            for window in ("primary", "secondary", "monthly", "5h", "7d", "30d", None):
                rows.extend(
                    conn.execute(
                        "SELECT window, used_percent, recorded_at, reset_at, window_minutes FROM usage_history "
                        "WHERE account_id=? AND window IS ? ORDER BY recorded_at DESC, id DESC LIMIT 1",
                        (a["id"], window),
                    ).fetchall()
                )
            usage[a["id"]] = rows
        log_cols = {r[1] for r in conn.execute("PRAGMA table_info(request_logs)")}
        filters = ["requested_at >= ?", "requested_at <= ?", "account_id IS NOT NULL", "length(trim(model)) > 0"]
        if "request_kind" in log_cols:
            filters.append("request_kind='normal'")
        if "model_source_id" in log_cols:
            filters.append("model_source_id IS NULL")
        # Luna traffic is the deployment's probe path, even when older rows
        # were persisted as request_kind=normal. It must not drive the public
        # normal-request health signal or its incident debounce.
        filters.append("lower(model) NOT LIKE '%luna%'")
        scope = " AND ".join(filters)
        params = (sql_time(now - settings.request_window_seconds), sql_time(now))
        rows = conn.execute(
            "SELECT model, COUNT(*) total, SUM(status='success') successes, SUM(status='cancelled') cancelled, "
            "SUM(status NOT IN ('success','cancelled')) errors, "
            "MAX(CASE WHEN status='success' THEN requested_at END) last_success_at "
            f"FROM request_logs WHERE {scope} GROUP BY model ORDER BY total DESC",
            params,
        ).fetchall()
        models = []
        for row in rows:
            m = dict(row)
            m["last_success_at"] = epoch(m["last_success_at"])
            m["error_percent"] = round(m["errors"] / m["total"] * 100, 2)
            models.append(m)
        first_col = "latency_first_output_ms" if "latency_first_output_ms" in log_cols else "latency_first_token_ms"
        timings = conn.execute(
            f"SELECT latency_ms, {first_col} first_ms FROM request_logs WHERE {scope} "
            "AND status='success' ORDER BY requested_at DESC LIMIT 10000",
            params,
        ).fetchall()
        totals = {k: sum(m[k] for m in models) for k in ("total", "successes", "cancelled", "errors")}
        successes = [m["last_success_at"] for m in models if m["last_success_at"] is not None]
        totals.update(
            {
                "error_percent": round(totals["errors"] / totals["total"] * 100, 2) if totals["total"] else None,
                "success_percent": round(totals["successes"] / totals["total"] * 100, 2) if totals["total"] else None,
                "last_success_at": max(successes) if successes else None,
                "first_output_p50_ms": percentile([r["first_ms"] for r in timings], 0.5),
                "duration_p95_ms": percentile([r["latency_ms"] for r in timings], 0.95),
                "timing_samples": len(timings),
                "window_seconds": settings.request_window_seconds,
                "timing_kind": "first_output" if first_col == "latency_first_output_ms" else "first_token",
                "models": models,
            }
        )
        return {"pool": pool_summary(accounts, usage, now, settings), "requests": totals}
    finally:
        conn.close()


def probe(check):
    start = time.monotonic()
    try:
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            response = client.get(check["url"], headers={"Accept": "application/json"})
        ok = response.status_code == 200 and response.json().get("status") == "ok"
        detail = "就绪检查通过" if ok else "就绪检查未通过"
    except httpx.HTTPError as exc:
        if "Operation not permitted" in str(exc) or "Permission denied" in str(exc):
            return {
                "id": check["id"],
                "name": check["name"],
                "status": "unknown",
                "detail": "探测器网络权限不足",
                "latency_ms": None,
            }
        ok, detail = False, "无法完成就绪检查"
    except (ValueError, TypeError, AttributeError):
        ok, detail = False, "无法完成就绪检查"
    return {
        "id": check["id"],
        "name": check["name"],
        "status": "operational" if ok else "outage",
        "detail": detail,
        "latency_ms": round((time.monotonic() - start) * 1000, 1),
    }


def collect(settings: Settings, now=None, probe_fn=probe):
    now = time.time() if now is None else now
    components = [probe_fn(check) for check in settings.checks]
    result = {"collected_at": now, "pool": None, "requests": None, "components": components}
    try:
        result.update(read_source(settings, now))
        components.append({"id": "source", "name": "监控数据", "status": "operational", "detail": "只读采集正常"})
        pool, requests = result["pool"], result["requests"]
        quota_status = (
            "outage"
            if not pool["active"] or (pool["quota_exhausted"] and not pool["quota_ready"] and not pool["quota_unknown"])
            else (
                "unknown"
                if pool["quota_unknown"]
                else "degraded"
                if pool["quota_exhausted"]
                or (
                    pool["lowest_remaining_percent"] is not None
                    and pool["lowest_remaining_percent"] < settings.low_quota_percent
                )
                else "operational"
            )
        )
        components.append(
            {
                "id": "quota",
                "name": "号池额度",
                "status": quota_status,
                "detail": "额度未知或过期"
                if quota_status == "unknown"
                else "额度不足"
                if quota_status in {"degraded", "outage"}
                else "近期额度样本正常",
            }
        )
        req_status = (
            "unknown"
            if not requests["total"] or (not requests["successes"] and not requests["errors"])
            else (
                "degraded"
                if requests["error_percent"] >= settings.high_error_percent
                and requests["total"] >= settings.min_requests
                else "operational"
                if requests["successes"]
                else "unknown"
            )
        )
        components.append(
            {
                "id": "requests",
                "name": "真实模型请求",
                "status": req_status,
                "detail": "近期有成功终态"
                if req_status == "operational"
                else "近期错误率升高"
                if req_status == "degraded"
                else "缺少足够的成功样本",
            }
        )
    except (sqlite3.Error, ValueError, OSError, KeyError, TypeError):
        components.extend(
            [
                {"id": "source", "name": "监控数据", "status": "unknown", "detail": "采集暂不可用"},
                {"id": "quota", "name": "号池额度", "status": "unknown", "detail": "等待采集恢复"},
                {"id": "requests", "name": "真实模型请求", "status": "unknown", "detail": "等待采集恢复"},
            ]
        )
    statuses = [c["status"] for c in components]
    result["status"] = next((s for s in ("outage", "degraded", "unknown") if s in statuses), "operational")
    return result
