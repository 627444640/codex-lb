from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
 id INTEGER PRIMARY KEY, collected_at REAL NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS snapshots_time ON snapshots(collected_at);
CREATE TABLE IF NOT EXISTS alert_state (
 component TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0,
 recoveries INTEGER NOT NULL DEFAULT 0, incident_id INTEGER);
CREATE TABLE IF NOT EXISTS incidents (
 id INTEGER PRIMARY KEY, component TEXT NOT NULL, title TEXT NOT NULL,
 severity TEXT NOT NULL, opened_at REAL NOT NULL, closed_at REAL);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
 body TEXT NOT NULL, created_at REAL NOT NULL, email_status TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at REAL NOT NULL,
 last_error TEXT, sent_at REAL);
CREATE TABLE IF NOT EXISTS notices (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
 level TEXT NOT NULL, status TEXT NOT NULL, starts_at REAL NOT NULL,
 ends_at REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (
 id INTEGER PRIMARY KEY, client_hash TEXT NOT NULL, attempted_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS login_attempts_time ON login_attempts(attempted_at);
CREATE TABLE IF NOT EXISTS availability_daily (
 day TEXT PRIMARY KEY, healthy INTEGER NOT NULL, observed INTEGER NOT NULL,
 samples INTEGER NOT NULL, first_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS monitor_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

TAIPEI = ZoneInfo("Asia/Taipei")
# Same relative weekly capacities as the inspected Codex LB quota contract.
WEEKLY_WEIGHTS = {
    "free": 1134,
    "plus": 7560,
    "business": 7560,
    "team": 7560,
    "edu": 7560,
    "pro": 50400,
    "prolite": 37800,
    "enterprise": 50400,
}


def weekly_capacity(pool):
    if pool is None:
        return None
    numerator = denominator = 0.0
    for plan in pool["plans"]:
        if not plan["active"]:
            continue
        weekly = next((w for w in plan["windows"] if w["key"] == "secondary"), None)
        if weekly is None and any(w["key"] == "monthly" for w in plan["windows"]):
            continue
        if (
            weekly is None
            or weekly["remaining_percent"] is None
            or weekly["known"] != weekly["expected"]
            or plan["plan"] not in WEEKLY_WEIGHTS
        ):
            return None
        weight = WEEKLY_WEIGHTS[plan["plan"]] * plan["active"]
        numerator += weight * weekly["remaining_percent"]
        denominator += weight
    return round(numerator / denominator, 2) if denominator else None


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings.validate()
        settings.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings.state_dir.chmod(0o700)
        if settings.state_db.is_symlink():
            raise ValueError("State database must not be a symlink")
        with self.db() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            if not conn.execute("SELECT 1 FROM monitor_meta WHERE key='daily-backfill-v1'").fetchone():
                for row in conn.execute("SELECT payload FROM snapshots").fetchall():
                    self._record_daily(conn, json.loads(row["payload"]))
                conn.execute("INSERT INTO monitor_meta VALUES ('daily-backfill-v1','done')")
        settings.state_db.chmod(0o600)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.settings.state_db, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def record(self, snapshot):
        now = snapshot["collected_at"]
        with self.db() as conn:
            conn.execute(
                "INSERT INTO snapshots(collected_at,payload) VALUES (?,?)",
                (now, json.dumps(snapshot, ensure_ascii=False, allow_nan=False)),
            )
            self._alerts(conn, snapshot)
            self._record_daily(conn, snapshot)
            cutoff = now - self.settings.retention_days * 86400
            conn.execute("DELETE FROM snapshots WHERE collected_at < ?", (cutoff,))
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            conn.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (now - 900,))
            conn.execute("DELETE FROM events WHERE created_at < ? AND email_status IN ('sent','disabled')", (cutoff,))
            conn.execute("DELETE FROM incidents WHERE closed_at < ?", (cutoff,))
            conn.execute(
                "DELETE FROM availability_daily WHERE day < ?",
                ((datetime.fromtimestamp(now, TAIPEI).date() - timedelta(days=365)).isoformat(),),
            )

    @staticmethod
    def _record_daily(conn, snapshot):
        at = snapshot["collected_at"]
        day = datetime.fromtimestamp(at, TAIPEI).date().isoformat()
        checks = [c for c in snapshot["components"] if c["id"] not in {"source", "quota", "requests"}]
        observed = int(bool(checks) and all(c["status"] != "unknown" for c in checks))
        healthy = int(bool(observed) and all(c["status"] == "operational" for c in checks))
        conn.execute(
            "INSERT INTO availability_daily(day,healthy,observed,samples,first_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET healthy=healthy+excluded.healthy, "
            "observed=observed+excluded.observed,samples=samples+1,first_at=min(first_at,excluded.first_at)",
            (day, healthy, observed, 1, at),
        )

    def _alerts(self, conn, snapshot):
        source_ok = any(c["id"] == "source" and c["status"] == "operational" for c in snapshot["components"])
        now = snapshot["collected_at"]
        for component in snapshot["components"]:
            key, status = component["id"], component["status"]
            if key in {"quota", "requests"} and not source_ok:
                conn.execute("UPDATE alert_state SET failures=0,recoveries=0 WHERE component=?", (key,))
                continue
            if key == "requests" and status == "unknown":
                conn.execute("UPDATE alert_state SET failures=0,recoveries=0 WHERE component=?", (key,))
                continue  # Idle traffic cannot prove failure or recovery.
            conn.execute("INSERT OR IGNORE INTO alert_state(component) VALUES (?)", (key,))
            row = conn.execute("SELECT * FROM alert_state WHERE component=?", (key,)).fetchone()
            bad = status != "operational"
            failures = row["failures"] + 1 if bad else 0
            recoveries = row["recoveries"] + 1 if not bad else 0
            incident_id = row["incident_id"]
            if failures >= self.settings.alert_failures and incident_id is None:
                title = f"{component['name']}：{component['detail']}"
                cursor = conn.execute(
                    "INSERT INTO incidents(component,title,severity,opened_at) VALUES (?,?,?,?)",
                    (key, title, "critical" if status == "outage" else "warning", now),
                )
                incident_id = cursor.lastrowid
                self._event(
                    conn,
                    f"incident:{incident_id}:open",
                    "[告警] " + title,
                    f"连续 {self.settings.alert_failures} 次采样异常。请查看状态页。",
                    now,
                )
            elif recoveries >= self.settings.alert_recoveries and incident_id is not None:
                conn.execute("UPDATE incidents SET closed_at=? WHERE id=?", (now, incident_id))
                conn.execute(
                    "UPDATE events SET email_status='superseded' WHERE event_key=? "
                    "AND email_status IN ('pending','retry')",
                    (f"incident:{incident_id}:open",),
                )
                self._event(
                    conn,
                    f"incident:{incident_id}:resolved",
                    f"[恢复] {component['name']}",
                    f"连续 {self.settings.alert_recoveries} 次采样恢复正常。",
                    now,
                )
                incident_id = None
            conn.execute(
                "UPDATE alert_state SET failures=?,recoveries=?,incident_id=? WHERE component=?",
                (min(failures, 100), min(recoveries, 100), incident_id, key),
            )

    def _event(self, conn, key, title, body, now):
        conn.execute(
            "INSERT OR IGNORE INTO events(event_key,title,body,created_at,email_status,next_attempt_at) "
            "VALUES (?,?,?,?,?,?)",
            (key, title, body, now, "pending" if self.settings.smtp_ready else "disabled", now),
        )

    def latest(self):
        with self.db() as conn:
            row = conn.execute("SELECT payload FROM snapshots ORDER BY collected_at DESC,id DESC LIMIT 1").fetchone()
        return json.loads(row["payload"]) if row else None

    def notices(self, public=False, now=None):
        now = time.time() if now is None else now
        with self.db() as conn:
            if public:
                rows = conn.execute(
                    "SELECT id,title,body,level,starts_at,ends_at FROM notices WHERE status='published' "
                    "AND starts_at<=? AND (ends_at IS NULL OR ends_at>?) ORDER BY starts_at DESC LIMIT 30",
                    (now, now),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM notices ORDER BY updated_at DESC LIMIT 100").fetchall()
        return [dict(r) for r in rows]

    def save_notice(self, data, notice_id=None):
        now = time.time()
        values = tuple(data[k] for k in ("title", "body", "level", "status", "starts_at", "ends_at"))
        with self.db() as conn:
            if notice_id is None:
                notice_id = conn.execute(
                    "INSERT INTO notices(title,body,level,status,starts_at,ends_at,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (*values, now, now),
                ).lastrowid
            else:
                changed = conn.execute(
                    "UPDATE notices SET title=?,body=?,level=?,status=?,starts_at=?,ends_at=?,updated_at=? WHERE id=?",
                    (*values, now, notice_id),
                ).rowcount
                if not changed:
                    return None
        return notice_id

    def incidents(self):
        with self.db() as conn:
            rows = conn.execute(
                "SELECT id,component,title,severity,opened_at,closed_at FROM incidents ORDER BY opened_at DESC LIMIT 30"
            ).fetchall()
        return [dict(r) for r in rows]

    def events(self):
        with self.db() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM events ORDER BY created_at DESC,id DESC LIMIT 100")]

    def history(self, now):
        today = datetime.fromtimestamp(now, TAIPEI).date()
        start = today - timedelta(days=90)
        with self.db() as conn:
            rows = {
                r["day"]: dict(r)
                for r in conn.execute(
                    "SELECT * FROM availability_daily WHERE day>=? AND day<=?", (start.isoformat(), today.isoformat())
                )
            }
        days = []
        healthy = observed = samples = 0
        for i in range(91):
            day = (start + timedelta(days=i)).isoformat()
            row = rows.get(day)
            valid = row["observed"] if row else 0
            days.append(
                {
                    "date": day,
                    "percent": round(row["healthy"] / valid * 100, 2) if valid else None,
                    "samples": row["samples"] if row else 0,
                    "observed": valid,
                }
            )
            if row:
                healthy += row["healthy"]
                observed += valid
                samples += row["samples"]
        return {
            "days": days,
            "samples": samples,
            "observed_checks": observed,
            "readiness_percent": round(healthy / observed * 100, 2) if observed else None,
            "since": min((r["first_at"] for r in rows.values()), default=None),
        }

    def public(self, now=None):
        now = time.time() if now is None else now
        s = self.latest()
        stale = not s or now - s["collected_at"] > max(3 * self.settings.poll_seconds, 120)
        if s is None:
            s = {"collected_at": None, "status": "unknown", "components": [], "pool": None, "requests": None}
        if stale:
            s["status"] = "unknown"
            s["pool"] = s["requests"] = None
            s["components"] = [
                {"id": c["id"], "name": c["name"], "status": "unknown", "detail": "采样已过期"} for c in s["components"]
            ]
        # Explicit output contract: never serialize Settings, auth, or SMTP objects.
        return {
            "title": self.settings.title,
            "status": s["status"],
            "collected_at": s["collected_at"],
            "stale": stale,
            "poll_seconds": self.settings.poll_seconds,
            "components": s["components"],
            "capacity": {"weekly_remaining_percent": weekly_capacity(s["pool"])},
            "requests": s["requests"],
            "history": self.history(now),
            "incidents": self.incidents(),
            "notices": self.notices(True, now),
            "timezone": "Asia/Taipei",
        }
