from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from monitor.config import Settings
from monitor.server import create_app
from monitor.store import Store


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.settings = Settings(source_db=root / "source.db", state_dir=root / "state", checks=())
        self.app = create_app(self.settings, run_collector=False)
        self.client = TestClient(self.app, base_url=self.settings.origin, client=("127.0.0.1", 10))
        self.headers = {"Authorization": f"Bearer {self.settings.control_token_file.read_text()}"}
        self.data = dict(
            code="TEST",
            title="Synthetic guide",
            scope="Synthetic symptom",
            cause="Synthetic cause",
            solutions=["First step", "Second step"],
            status="draft",
            sort_order=5,
        )

    def save(self, data=None):
        response = self.client.post("/internal/guides", json=data or self.data, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def page(self):
        return self.client.get("/static/faq.html").text

    def test_seed_once_and_full_lifecycle_survives_restart(self):
        initial = self.client.get("/internal/guides", headers=self.headers).json()["guides"]
        self.assertEqual(len(initial), 2)
        self.assertIn('id="error-413"', self.page())
        row = self.save()
        self.assertNotIn("Synthetic guide", self.page())
        response = self.client.put(
            f"/internal/guides/{row['id']}",
            json={**self.data, "status": "published", "revision": row["revision"]},
            headers=self.headers,
        )
        row = response.json()
        self.assertIn("Synthetic guide", self.page())
        self.assertLess(self.page().index("Synthetic guide"), self.page().index('id="error-413"'))
        self.assertEqual(
            self.client.put(
                f"/internal/guides/{row['id']}", json={**self.data, "revision": 1}, headers=self.headers
            ).status_code,
            409,
        )
        row = self.client.request(
            "DELETE", f"/internal/guides/{row['id']}", json={"revision": row["revision"]}, headers=self.headers
        ).json()
        self.assertIsNotNone(row["deleted_at"])
        self.assertNotIn("Synthetic guide", self.page())
        restarted = create_app(self.settings, run_collector=False)
        after = restarted.state.guides.list()
        self.assertEqual(len(after), 3)
        self.assertIsNotNone(after[0].deleted_at)
        restored = self.client.post(
            f"/internal/guides/{row['id']}/restore", json={"revision": row["revision"]}, headers=self.headers
        ).json()
        self.assertEqual(restored["status"], "draft")
        self.assertNotIn("Synthetic guide", self.page())

    def test_seed_deletion_is_not_resurrected(self):
        row = self.app.state.guides.list()[0]
        self.client.request(
            "DELETE", f"/internal/guides/{row.id}", json={"revision": row.revision}, headers=self.headers
        )
        app = create_app(self.settings, run_collector=False)
        self.assertEqual(len(app.state.guides.list()), 2)
        self.assertEqual(len(app.state.guides.list(public=True)), 1)

    def test_upgrade_preserves_existing_monitor_data(self):
        root = Path(self.temp.name)
        settings = Settings(source_db=root / "legacy-source.db", state_dir=root / "legacy-monitor", checks=())
        old_store = Store(settings)
        notice_id = old_store.save_notice(
            dict(
                title="Existing notice",
                body="Preserve this content",
                level="info",
                status="draft",
                starts_at=1,
                ends_at=None,
            )
        )
        with old_store.db() as conn:
            self.assertIsNone(
                conn.execute("SELECT name FROM sqlite_master WHERE name='troubleshooting_guides'").fetchone()
            )
        upgraded = create_app(settings, run_collector=False)
        notice = upgraded.state.store.notices()[0]
        self.assertEqual(notice["id"], notice_id)
        self.assertEqual(notice["body"], "Preserve this content")
        self.assertEqual(len(upgraded.state.guides.list()), 2)

    def test_private_routes_require_local_service_auth(self):
        for method, path in (
            ("GET", "/internal/guides"),
            ("POST", "/internal/guides"),
            ("PUT", "/internal/guides/1"),
            ("DELETE", "/internal/guides/1"),
            ("POST", "/internal/guides/1/restore"),
        ):
            with self.subTest(method=method):
                self.assertEqual(self.client.request(method, path, json={}).status_code, 401)
        remote = TestClient(self.app, base_url=self.settings.origin, client=("203.0.113.7", 10))
        self.assertEqual(remote.get("/internal/guides", headers=self.headers).status_code, 401)

    def test_public_html_escapes_content_and_keeps_drafts_private(self):
        self.save({**self.data, "title": "PRIVATE DRAFT"})
        row = self.save(
            {
                **self.data,
                "title": '<img src=x onerror="alert(1)">',
                "status": "published",
                "solutions": ["<script>alert(1)</script>"],
                "endpoint_url": "https://example.invalid/v1",
            }
        )
        page = self.page()
        self.assertNotIn("PRIVATE DRAFT", page)
        self.assertIn("&lt;img", page)
        self.assertNotIn("<img src=x", page)
        self.assertNotIn("<script>alert(1)", page)
        self.assertIn(f'data-copy-target="guide-endpoint-{row["id"]}"', page)
        self.assertNotIn("/api/status", page)
        self.assertNotIn(self.headers["Authorization"], page)
        self.assertNotIn("deleted_at", page)
        self.assertNotIn("revision", page)
        self.assertEqual(self.client.get("/health").status_code, 503)
        self.assertEqual(self.client.get("/static/troubleshooting.html").status_code, 200)

    def test_validation_and_conflicts_do_not_overwrite_content(self):
        for url in ("javascript:alert(1)", "data:text/html,x", "https://user:secret@example.invalid"):
            self.assertEqual(
                self.client.post(
                    "/internal/guides", json={**self.data, "endpoint_url": url}, headers=self.headers
                ).status_code,
                422,
            )
        self.assertEqual(
            self.client.post(
                "/internal/guides", json={**self.data, "solutions": ["   "]}, headers=self.headers
            ).status_code,
            422,
        )
        row = self.save()
        self.assertEqual(
            self.client.put(f"/internal/guides/{row['id']}", json=self.data, headers=self.headers).status_code, 409
        )
        self.assertEqual(
            self.client.put(
                "/internal/guides/999999", json={**self.data, "revision": 1}, headers=self.headers
            ).status_code,
            404,
        )
        row = self.client.put(
            f"/internal/guides/{row['id']}",
            json={**self.data, "status": "withdrawn", "revision": 1},
            headers=self.headers,
        ).json()
        self.assertEqual(row["status"], "withdrawn")
        self.assertNotIn("Synthetic guide", self.page())


if __name__ == "__main__":
    unittest.main()
