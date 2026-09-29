from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_guides
from fastapi.testclient import TestClient

from monitor.server import create_app


class FAQTests(unittest.TestCase):
    setUp = test_guides.GuideTests.setUp

    def test_page_and_navigation_use_faq_without_chat_or_model_assets(self):
        response = self.client.get("/static/faq.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>Codex LB · 常见问题</title>", response.text)
        self.assertIn("<h1>常见问题</h1>", response.text)
        self.assertIn('id="error-websocket-payload-too-large"', response.text)
        self.assertIn('src="/static/faq.js"', response.text)
        self.assertNotIn("assistant-", response.text)
        self.assertNotIn("<textarea", response.text)
        self.assertNotIn("错误排查", response.text)
        overview = self.client.get("/").text
        self.assertIn('href="/static/faq.html">常见问题</a>', overview)
        self.assertNotIn("错误排查", overview)

    def test_old_address_redirects_and_retains_published_anchor_targets(self):
        old = self.client.get("/static/troubleshooting.html", follow_redirects=False)
        self.assertEqual(old.status_code, 308)
        self.assertEqual(old.headers["location"], "/static/faq.html")
        page = self.client.get(old.headers["location"])
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="error-413"', page.text)

    def test_old_model_configuration_is_not_read_and_retired_routes_do_not_call_out(self):
        legacy = self.settings.state_dir / "troubleshooting-assistant.json"
        secret = "synthetic-retired-key-not-valid-anywhere"
        legacy.write_text(json.dumps({"enabled": True, "api_key": secret, "base_url": "https://unused.invalid/v1"}))
        legacy.chmod(0o600)
        original_read = Path.read_text

        def guarded_read(path, *args, **kwargs):
            if path == legacy:
                raise AssertionError("The retired model configuration must not be read")
            return original_read(path, *args, **kwargs)

        with (
            patch.object(Path, "read_text", guarded_read),
            patch("socket.create_connection", side_effect=AssertionError("FAQ must not call a model")),
        ):
            app = create_app(self.settings, run_collector=False)
            client = TestClient(app, base_url=self.settings.origin, client=("127.0.0.1", 10))
            self.assertEqual(client.get("/static/faq.html").status_code, 200)
            for method, path in (
                ("GET", "/api/troubleshooting/assistant"),
                ("POST", "/api/troubleshooting/chat"),
                ("GET", "/internal/assistant"),
                ("PUT", "/internal/assistant"),
                ("POST", "/internal/assistant/test"),
            ):
                with self.subTest(method=method, path=path):
                    response = client.request(method, path, json={}, headers=self.headers)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn(secret, response.text)
            for asset in ("assistant-stream.mjs", "troubleshooting.js"):
                self.assertEqual(client.get("/static/" + asset).status_code, 404)
        with self.app.state.store.db() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='assistant_usage'").fetchone())

    def test_upgrade_preserves_but_does_not_update_retired_usage_state(self):
        with self.app.state.store.db() as db:
            db.execute("CREATE TABLE assistant_usage (day TEXT PRIMARY KEY, model_calls INTEGER NOT NULL)")
            db.execute("INSERT INTO assistant_usage VALUES ('2026-09-29', 7)")
        app = create_app(self.settings, run_collector=False)
        client = TestClient(app, base_url=self.settings.origin, client=("127.0.0.1", 10))
        self.assertEqual(client.get("/static/faq.html").status_code, 200)
        with app.state.store.db() as db:
            self.assertEqual(db.execute("SELECT model_calls FROM assistant_usage").fetchone()[0], 7)
