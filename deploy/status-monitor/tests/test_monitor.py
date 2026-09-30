from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from monitor.collector import collect, read_source, sql_time
from monitor.config import Settings, load_settings
from monitor.mailer import deliver_pending
from monitor.server import create_app
from monitor.store import Store


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.db"
        self.now = time.time()
        self.settings = Settings(source_db=self.source, state_dir=self.root / "monitor", checks=())
        with self.source_connection() as c:
            c.executescript(
                (
                    "\n            CREATE TABLE accounts(id TEXT,pl"
                    "an_type TEXT,status TEXT,delete_requested_at "
                    "TEXT,\n                email TEXT DEFAULT 'pri"
                    "vate@example.invalid',access_token_encrypted "
                    "TEXT DEFAULT 'secret-token-marker');\n        "
                    "    CREATE TABLE usage_history(id INTEGER PRI"
                    "MARY KEY,account_id TEXT,window TEXT,used_per"
                    "cent REAL,\n                recorded_at TEXT,r"
                    "eset_at INTEGER,window_minutes INTEGER);\n    "
                    "        CREATE TABLE request_logs(id INTEGER "
                    "PRIMARY KEY,account_id TEXT,model TEXT,status"
                    " TEXT,\n                requested_at TEXT,requ"
                    "est_kind TEXT,model_source_id TEXT,latency_ms"
                    " REAL,\n                latency_first_output_m"
                    "s REAL,client_ip TEXT DEFAULT 'private-ip-mar"
                    "ker',error_message TEXT DEFAULT 'private-erro"
                    "r-marker');\n            INSERT INTO accounts("
                    "id,plan_type,status) VALUES ('private-account"
                    "-id','pro','active');\n            "
                )
            )
        self.usage("primary", 20, minutes=10080)
        self.usage("secondary", 0, minutes=0)

    @contextmanager
    def source_connection(self):
        conn = sqlite3.connect(self.source)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def usage(self, window, used, minutes=300, at=None, reset=None, account="private-account-id"):
        with self.source_connection() as c:
            c.execute(
                (
                    "INSERT INTO usage_history(account_id,window,u"
                    "sed_percent,recorded_at,reset_at,window_minut"
                    "es) VALUES (?,?,?,?,?,?)"
                ),
                (
                    account,
                    window,
                    used,
                    sql_time(self.now if at is None else at),
                    self.now + 7200 if reset is None else reset,
                    minutes,
                ),
            )

    def request(
        self, status="success", kind="normal", model="test-model", source=None, at=None, account="private-account-id"
    ):
        with self.source_connection() as c:
            c.execute(
                (
                    "INSERT INTO request_logs(account_id,model,sta"
                    "tus,requested_at,request_kind,model_source_id"
                    ",latency_ms,latency_first_output_ms) VALUES ("
                    "?,?,?,?,?,?,?,?)"
                ),
                (account, model, status, sql_time(self.now - 1 if at is None else at), kind, source, 1234, 123),
            )

    def snapshot(self, status="operational", ts=None, component="gateway"):
        return {
            "collected_at": self.now if ts is None else ts,
            "status": status,
            "pool": {},
            "requests": {},
            "components": [
                {"id": component, "name": "测试服务", "status": status, "detail": "模拟检查结果"},
                {"id": "source", "name": "监控数据", "status": "operational", "detail": "只读采集正常"},
            ],
        }


class CollectorTests(Fixture):
    def test_allowed_hosts_accepts_lan_aliases_and_rejects_malformed_values(self):
        self.assertEqual(
            Settings(
                source_db=self.source,
                state_dir=self.root / "lan-monitor",
                origin="https://192.168.3.182:2467",
                allowed_hosts=("123Mac.local",),
                checks=(),
            )
            .validate()
            .allowed_hosts,
            ("123Mac.local",),
        )
        for host in ("*", "status.example/path", "status.example:2467", "status example"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                Settings(
                    source_db=self.source,
                    state_dir=self.root / "lan-monitor",
                    origin="https://192.168.3.182:2467",
                    allowed_hosts=(host,),
                    checks=(),
                ).validate()

    def test_actual_weekly_primary_not_fabricated_five_hours(self):
        p = read_source(self.settings, self.now)["pool"]
        self.assertEqual(p["quota_ready"], 1)
        self.assertEqual(p["plans"][0]["windows"][0]["remaining_percent"], 80)
        self.assertEqual([w["key"] for w in p["plans"][0]["windows"]], ["secondary"])

    def test_monthly_plan_has_no_weekly_or_five_hour_window(self):
        with self.source_connection() as c:
            c.execute("UPDATE accounts SET plan_type='free'")
        self.usage("monthly", 5, minutes=43200, at=self.now + 6)
        windows = read_source(self.settings, self.now + 6)["pool"]["plans"][0]["windows"]
        self.assertEqual([w["key"] for w in windows], ["monthly"])

    def test_old_monthly_does_not_hide_new_weekly(self):
        self.usage("monthly", 5, minutes=43200, at=self.now - 86400)
        self.assertEqual(read_source(self.settings, self.now)["pool"]["quota_ready"], 1)

    def test_unknown_and_expired_reset_never_become_full_capacity(self):
        for at, reset in [(self.now - 901, self.now + 100), (self.now, self.now - 1)]:
            with self.subTest(at=at):
                with self.source_connection() as c:
                    c.execute("UPDATE usage_history SET recorded_at=?,reset_at=?", (sql_time(at), reset))
                p = read_source(self.settings, self.now)["pool"]
                self.assertEqual(p["quota_unknown"], 1)
                self.assertEqual(p["quota_ready"], 0)
                self.assertIsNone(p["plans"][0]["windows"][0]["remaining_percent"])

    def test_mixed_plans_are_not_averaged(self):
        with self.source_connection() as c:
            c.execute("INSERT INTO accounts(id,plan_type,status) VALUES ('plus-id','plus','active')")
        self.usage("primary", 90, minutes=10080, account="plus-id")
        p = read_source(self.settings, self.now)["pool"]
        self.assertEqual([g["plan"] for g in p["plans"]], ["plus", "pro"])
        self.assertEqual([g["windows"][0]["remaining_percent"] for g in p["plans"]], [10, 80])

    def test_pending_deletion_hidden_and_paused_not_available(self):
        with self.source_connection() as c:
            c.execute(
                (
                    "INSERT INTO accounts(id,plan_type,status,dele"
                    "te_requested_at) VALUES ('deleted','pro','act"
                    "ive','2026-09-28')"
                )
            )
            c.execute("UPDATE accounts SET status='paused' WHERE id='private-account-id'")
        p = read_source(self.settings, self.now)["pool"]
        self.assertEqual((p["total"], p["active"], p["quota_ready"]), (1, 0, 0))

    def test_cancellations_remain_in_denominator_not_error_numerator(self):
        for status in ("success", "cancelled", "cancelled", "error"):
            self.request(status)
        r = read_source(self.settings, self.now)["requests"]
        self.assertEqual((r["total"], r["successes"], r["errors"], r["cancelled"]), (4, 1, 1, 2))
        self.assertEqual(r["error_percent"], 25)

    def test_non_model_warmup_external_and_old_traffic_excluded(self):
        self.request()
        self.request(kind="warmup")
        self.request(model="")
        self.request(source="external-source")
        self.request(at=self.now - 901)
        self.request(account=None)
        self.assertEqual(read_source(self.settings, self.now)["requests"]["total"], 1)

    def test_no_samples_cannot_assert_business_available(self):
        s = collect(self.settings, self.now)
        c = next(c for c in s["components"] if c["id"] == "requests")
        self.assertEqual(c["status"], "unknown")
        self.assertIsNone(s["requests"]["error_percent"])

    def test_collect_does_not_modify_source_or_return_private_fields(self):
        self.request()
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        text = json.dumps(collect(self.settings, self.now))
        self.assertEqual(before, hashlib.sha256(self.source.read_bytes()).hexdigest())
        for marker in (
            "private-account-id",
            "private@example.invalid",
            "secret-token-marker",
            "private-ip-marker",
            "private-error-marker",
        ):
            self.assertNotIn(marker, text)

    def test_source_failure_keeps_unknown_not_false_green(self):
        s = collect(replace(self.settings, source_db=self.root / "missing.db"), self.now)
        self.assertEqual(s["status"], "unknown")
        self.assertIsNone(s["pool"])
        self.assertFalse((self.root / "missing.db").exists())

    def test_network_permission_is_observer_unknown(self):
        from monitor.collector import probe

        with patch("httpx.Client.get", side_effect=httpx.ConnectError("[Errno 1] Operation not permitted")):
            r = probe({"id": "gateway", "name": "网关", "url": "http://127.0.0.1/health"})
        self.assertEqual(r["status"], "unknown")


class StateTests(Fixture):
    def setUp(self):
        super().setUp()
        self.store = Store(self.settings)

    def test_debounce_deduplicates_and_persists_across_restart(self):
        for i in range(2):
            self.store.record(self.snapshot("outage", self.now + i))
        self.assertEqual(self.store.events(), [])
        restarted = Store(self.settings)
        for i in range(2, 9):
            restarted.record(self.snapshot("outage", self.now + i))
        self.assertEqual(len(restarted.events()), 1)
        self.assertEqual(restarted.events()[0]["email_status"], "disabled")
        restarted.record(self.snapshot("operational", self.now + 9))
        self.assertIsNone(restarted.incidents()[0]["closed_at"])
        restarted.record(self.snapshot("operational", self.now + 10))
        self.assertEqual(len(restarted.events()), 2)
        self.assertIsNotNone(restarted.incidents()[0]["closed_at"])

    def test_idle_requests_reset_debounce_without_false_recovery(self):
        for i in range(2):
            self.store.record(self.snapshot("degraded", self.now + i, "requests"))
        self.store.record(self.snapshot("unknown", self.now + 2, "requests"))
        self.store.record(self.snapshot("degraded", self.now + 3, "requests"))
        self.assertEqual(self.store.events(), [])
        for i in range(4, 6):
            self.store.record(self.snapshot("degraded", self.now + i, "requests"))
        self.store.record(self.snapshot("unknown", self.now + 6, "requests"))
        self.assertIsNone(self.store.incidents()[0]["closed_at"])

    def test_stale_snapshot_hides_old_green_values(self):
        self.store.record(self.snapshot())
        result = self.store.public(self.now + 181)
        self.assertTrue(result["stale"])
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("pool", result)
        self.assertIsNone(result["capacity"]["weekly_remaining_percent"])
        self.assertIsNone(result["requests"])

    def test_history_has_no_invented_samples(self):
        self.store.record(self.snapshot())
        history = self.store.history(self.now)
        self.assertEqual(sum(b["samples"] for b in history["days"]), 1)
        self.assertEqual(sum(b["percent"] is None for b in history["days"]), 90)

    def test_notice_scheduling_draft_expiry_and_withdrawal(self):
        base = {
            "title": "标题",
            "body": "内容",
            "level": "info",
            "status": "draft",
            "starts_at": self.now - 1,
            "ends_at": None,
        }
        id_ = self.store.save_notice(base)
        self.assertEqual(self.store.notices(True, self.now), [])
        self.store.save_notice({**base, "status": "published", "starts_at": self.now + 100}, id_)
        self.assertEqual(self.store.notices(True, self.now), [])
        self.assertEqual(len(self.store.notices(True, self.now + 101)), 1)
        self.store.save_notice({**base, "status": "published", "ends_at": self.now + 10}, id_)
        self.assertEqual(self.store.notices(True, self.now + 11), [])
        self.store.save_notice({**base, "status": "withdrawn"}, id_)
        self.assertEqual(self.store.notices(True, self.now), [])

    def test_retention_and_source_state_separation(self):
        with self.assertRaises(ValueError):
            Settings(source_db=self.source, state_dir=self.root).validate()
        self.store.record(self.snapshot(ts=self.now - 91 * 86400))
        self.store.record(self.snapshot())
        with self.store.db() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM snapshots").fetchone()[0], 1)


class ControlTests(Fixture):
    def setUp(self):
        super().setUp()
        from dataclasses import asdict

        self.settings.state_dir.mkdir()
        self.config_path = self.settings.state_dir / "config.json"
        data = asdict(self.settings)
        data["source_db"], data["state_dir"] = str(self.source), str(self.settings.state_dir)
        self.config_path.write_text(json.dumps(data))
        self.config_path.chmod(0o600)
        self.app = create_app(self.settings, run_collector=False, config_path=self.config_path)
        self.store = self.app.state.store
        self.client = TestClient(self.app, base_url=self.settings.origin, client=("127.0.0.1", 32100))
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + self.settings.control_token_file.read_text()}

    def test_public_has_no_account_counts_and_no_second_admin(self):
        self.store.record(collect(self.settings, self.now))
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["capacity"], {"weekly_remaining_percent": 80})
        for key in ("pool", "quota_ready", "active", "private-account-id", "smtp", "token_file"):
            self.assertNotIn(key, response.text)
        for path in ("/admin", "/api/admin/overview", "/static/admin.html", "/static/admin.js"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_trusted_host_accepts_configured_lan_aliases_only(self):
        settings = Settings(
            source_db=self.source,
            state_dir=self.root / "lan-host-monitor",
            origin="https://192.168.3.182:2467",
            allowed_hosts=("123Mac.local",),
            checks=(),
        )
        app = create_app(settings, run_collector=False)
        with TestClient(app, base_url=settings.origin, client=("192.168.3.88", 32100)) as lan:
            self.assertEqual(lan.get("/").status_code, 200)
        with TestClient(app, base_url="https://123Mac.local:2467", client=("192.168.3.88", 32100)) as alias:
            self.assertEqual(alias.get("/static/faq.html").status_code, 200)
        with TestClient(app, base_url="https://unlisted.example:2467", client=("192.168.3.88", 32100)) as unknown:
            self.assertEqual(unknown.get("/").status_code, 400)

    def test_control_requires_private_token_and_loopback_peer(self):
        self.assertEqual(self.client.get("/internal/settings").status_code, 401)
        self.assertEqual(
            self.client.get("/internal/settings", headers={"Authorization": "Bearer wrong"}).status_code, 401
        )
        self.assertEqual(self.client.get("/internal/settings", headers=self.headers).status_code, 200)
        with TestClient(self.app, base_url=self.settings.origin, client=("203.0.113.3", 1234)) as remote:
            self.assertEqual(remote.get("/internal/settings", headers=self.headers).status_code, 401)

    def test_notice_lifecycle_uses_iso_dates_and_read_only_public_page(self):
        from datetime import datetime, timezone

        notice = {
            "title": "测试维护",
            "body": "<script>untrusted text</script>",
            "level": "maintenance",
            "status": "draft",
            "starts_at": datetime.fromtimestamp(self.now - 1, timezone.utc).isoformat(),
            "ends_at": None,
        }
        response = self.client.post("/internal/notices", json=notice, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        id_ = response.json()["id"]
        self.assertEqual(self.client.get("/api/status").json()["notices"], [])
        self.assertEqual(
            self.client.put(
                f"/internal/notices/{id_}", json={**notice, "status": "published"}, headers=self.headers
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/status").json()["notices"][0]["body"], notice["body"])
        private = self.client.get("/internal/settings", headers=self.headers).json()
        self.assertIn("T", private["notices"][0]["starts_at"])
        self.client.put(f"/internal/notices/{id_}", json={**notice, "status": "withdrawn"}, headers=self.headers)
        self.assertEqual(self.client.get("/api/status").json()["notices"], [])

    def test_email_secret_persists_without_echo_and_blank_preserves_it(self):
        payload = {
            "enabled": True,
            "host": "smtp.example.invalid",
            "port": 465,
            "tls": "ssl",
            "sender": "sender@example.invalid",
            "username": "sender@example.invalid",
            "recipients": ["recipient@example.invalid"],
            "password": "private-smtp-secret",
        }
        response = self.client.put("/internal/email", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["password_configured"])
        self.assertNotIn("private-smtp-secret", response.text)
        saved = load_settings(self.config_path)
        secret_path = Path(saved.smtp["password_file"])
        self.assertEqual(secret_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(secret_path.read_text(), "private-smtp-secret")
        response = self.client.put(
            "/internal/email", json={**payload, "password": None, "enabled": False}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        after = load_settings(self.config_path)
        self.assertEqual(after.smtp["password_file"], str(secret_path))
        self.assertFalse(after.smtp["enabled"])
        self.assertNotIn("private-smtp-secret", self.client.get("/internal/settings", headers=self.headers).text)
        self.assertNotIn("sender@example.invalid", self.client.get("/api/status").text)

    def test_invalid_secret_payload_does_not_echo_secrets(self):
        response = self.client.put("/internal/email", json={"password": "do-not-echo-this"}, headers=self.headers)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("do-not-echo-this", response.text)
        self.assertEqual(
            self.client.post(
                "/internal/notices", content="x" * 21000, headers={**self.headers, "Content-Type": "application/json"}
            ).status_code,
            413,
        )

    def test_calendar_uses_taipei_midnight_and_ignores_unknown_probes(self):
        from datetime import datetime, timezone

        before = datetime(2026, 9, 27, 15, 59, tzinfo=timezone.utc).timestamp()
        after = before + 120
        self.store.record(self.snapshot("operational", before))
        self.store.record(self.snapshot("outage", after))
        self.store.record(self.snapshot("unknown", after + 1))
        days = {d["date"]: d for d in self.store.history(after + 2)["days"]}
        self.assertEqual(days["2026-09-27"]["percent"], 100)
        self.assertEqual(days["2026-09-28"]["percent"], 0)
        self.assertEqual(days["2026-09-28"]["observed"], 1)
        self.assertEqual(days["2026-09-28"]["samples"], 2)
        self.assertIsNone(days["2026-09-26"]["percent"])
        restarted = Store(self.settings)
        self.assertEqual(restarted.history(after + 2)["days"], self.store.history(after + 2)["days"])

    def test_weighted_weekly_percentage_and_incomplete_data(self):
        from monitor.store import weekly_capacity

        with self.source_connection() as c:
            c.execute("INSERT INTO accounts(id,plan_type,status) VALUES ('plus-id','plus','active')")
        self.usage("primary", 0, minutes=10080, account="plus-id")
        pool = read_source(self.settings, self.now)["pool"]
        self.assertAlmostEqual(weekly_capacity(pool), 82.61)
        pool["plans"][0]["windows"][0]["known"] = 0
        self.assertIsNone(weekly_capacity(pool))


class EmailTests(Fixture):
    def setUp(self):
        super().setUp()
        self.smtp = {
            "enabled": True,
            "host": "smtp.example.invalid",
            "sender": "test@example.invalid",
            "recipients": ["recipient@example.invalid"],
            "tls": "ssl",
        }
        self.store = Store(replace(self.settings, smtp=self.smtp))
        for i in range(3):
            self.store.record(self.snapshot("outage", self.now + i))

    def test_retry_is_bounded_and_success_does_not_resend(self):
        sent = []

        def sender(settings, event):
            sent.append(event["id"])

        deliver_pending(self.store, self.now + 3, sender)
        deliver_pending(self.store, self.now + 4, sender)
        self.assertEqual(sent, [1])
        self.assertEqual(self.store.events()[0]["email_status"], "sent")

    def test_retry_backoff_and_redacted_failure(self):
        def failed(*_):
            raise OSError("secret smtp credential must not leak")

        deliver_pending(self.store, self.now + 3, failed)
        first = self.store.events()[0]
        self.assertEqual(first["email_status"], "retry")
        self.assertNotIn("secret", first["last_error"])
        deliver_pending(self.store, self.now + 4, failed)
        self.assertEqual(self.store.events()[0]["attempts"], 1)
        for i in range(4):
            deliver_pending(self.store, self.now + (i + 1) * 4000, failed)
        self.assertEqual(self.store.events()[0]["email_status"], "failed")
        self.assertEqual(self.store.events()[0]["attempts"], 5)

    def test_recovery_cancels_stale_unsent_outage(self):
        self.store.record(self.snapshot(ts=self.now + 4))
        self.store.record(self.snapshot(ts=self.now + 5))
        self.assertEqual(
            {e["event_key"].split(":")[-1]: e["email_status"] for e in self.store.events()},
            {"open": "superseded", "resolved": "pending"},
        )

    def test_disabled_notifications_are_not_backfilled(self):
        other = Store(replace(self.settings, state_dir=self.root / "disabled", smtp={}))
        for i in range(3):
            other.record(self.snapshot("outage", self.now + i))
        enabled = Store(replace(other.settings, smtp=self.smtp))
        sent = []
        deliver_pending(enabled, self.now + 10, lambda *_: sent.append(1))
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
