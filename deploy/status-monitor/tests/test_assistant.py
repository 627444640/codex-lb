from __future__ import annotations

import asyncio
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from monitor.assistant import redact_credentials
from monitor.config import Settings
from monitor.guides import GuideWrite
from monitor.server import create_app

SYNTHETIC_KEY = "test-only-credential-not-valid-anywhere"


def sse_response(answer):
    content = json.dumps(answer, ensure_ascii=False)
    event = {"choices": [{"index": 0, "delta": {"content": content}, "finish_reason": "stop"}]}
    return httpx.Response(
        200,
        headers={"Content-Type": "text/event-stream"},
        content=("data: " + json.dumps(event, ensure_ascii=False) + "\n\ndata: [DONE]\n\n").encode(),
    )


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.settings = Settings(source_db=root / "unused.db", state_dir=root / "state", checks=())
        self.app = create_app(self.settings, run_collector=False)
        self.client = TestClient(self.app, base_url=self.settings.origin, client=("127.0.0.1", 10))
        self.headers = {"Authorization": "Bearer " + self.settings.control_token_file.read_text()}
        self.config = {
            "enabled": True,
            "base_url": "http://127.0.0.1:2455/v1",
            "model": "synthetic-model",
            "api_key": SYNTHETIC_KEY,
            "requests_per_minute": 60,
            "daily_request_limit": 200,
        }

    def configure(self, **changes):
        response = self.client.put("/internal/assistant", headers=self.headers, json={**self.config, **changes})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(SYNTHETIC_KEY, response.text)
        return response.json()

    def mock_model(self, callback=None):
        real_client = httpx.AsyncClient

        def handler(request):
            wire = json.loads(request.content)
            context = json.loads(wire["messages"][-1]["content"])
            if callback:
                result = callback(wire, context)
                if result is not None:
                    return result
            evidence = context["published_guides"]
            ids = [evidence[0]["id"]] if evidence else []
            answer = {"answer": "Synthetic grounded answer", "source_ids": ids}
            return sse_response(answer)

        return patch(
            "monitor.assistant.httpx.AsyncClient",
            lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
        )

    def ask(self, question="WebSocket payload_too_large", **extra):
        return self.client.post("/api/troubleshooting/chat", json={"question": question, **extra})

    def test_disabled_and_missing_key_preserve_guide_page(self):
        response = self.client.get("/api/troubleshooting/assistant")
        self.assertEqual(response.json(), {"enabled": False, "max_question_chars": 2000})
        self.assertEqual(self.ask().status_code, 503)
        self.assertEqual(self.client.get("/static/troubleshooting.html").status_code, 200)
        self.assertEqual(self.client.post("/internal/assistant/test", headers=self.headers, json={}).status_code, 503)

    def test_admin_configuration_keeps_key_and_requires_replacement_on_destination_change(self):
        saved = self.configure()
        self.assertTrue(saved["key_configured"])
        self.assertEqual(stat.S_IMODE(self.app.state.assistant.settings.path.stat().st_mode), 0o600)
        self.configure(api_key=None, model="another-synthetic-model")
        self.assertEqual(self.app.state.assistant.settings.read().api_key.get_secret_value(), SYNTHETIC_KEY)
        response = self.client.put(
            "/internal/assistant",
            headers=self.headers,
            json={**self.config, "api_key": None, "base_url": "https://example.invalid/v1"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.app.state.assistant.settings.read().base_url, self.config["base_url"])
        self.configure(api_key=None, clear_key=True, enabled=False)
        self.assertFalse(self.client.get("/internal/assistant", headers=self.headers).json()["key_configured"])

    def test_default_and_replacement_persist_exactly_one_model_used_by_chat(self):
        base = "/internal/assistant"
        initial = self.client.get(base, headers=self.headers).json()
        self.assertEqual(initial["model"], "mercury-2.5")
        self.assertFalse(initial["enabled"])
        self.assertFalse(initial["key_configured"])
        self.configure(model="mercury2.5")
        saved = self.configure(api_key=None, model=" provider/replacement-v2:latest ")
        self.assertEqual(saved["model"], "provider/replacement-v2:latest")
        restarted = create_app(self.settings, run_collector=False)
        client = TestClient(restarted, base_url=self.settings.origin, client=("127.0.0.1", 10))
        self.assertEqual(client.get(base, headers=self.headers).json()["model"], saved["model"])
        persisted = json.loads(self.app.state.assistant.settings.path.read_text())
        self.assertEqual(persisted["model"], saved["model"])
        self.assertNotIn("models", persisted)
        calls = []
        with self.mock_model(lambda wire, context: calls.append(wire["model"])):
            self.assertEqual(self.ask().status_code, 200)
            self.assertEqual(self.client.post(base + "/test", headers=self.headers, json={}).status_code, 200)
        self.assertEqual(calls, [saved["model"], saved["model"]])

    def test_invalid_model_saves_leave_the_previous_configuration_unchanged(self):
        self.configure(model="mercury2.5", enabled=False)
        original = self.app.state.assistant.settings.path.read_bytes()
        invalid_models = (
            "",
            "   ",
            None,
            123,
            ["mercury2.5", "second"],
            {"model": "mercury2.5"},
            "mercury2.5 second",
            "mercury2.5\nsecond",
            "mercury2.5,second",
            "mercury2.5;second",
            "mercury2.5，second",
            "mercury2.5|second",
            '["mercury2.5"]',
            "x" * 121,
        )
        for value in invalid_models:
            with self.subTest(model=value):
                response = self.client.put(
                    "/internal/assistant", headers=self.headers, json={**self.config, "enabled": False, "model": value}
                )
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(SYNTHETIC_KEY, response.text)
                self.assertEqual(self.app.state.assistant.settings.path.read_bytes(), original)
        response = self.client.put(
            "/internal/assistant", headers=self.headers, json={**self.config, "models": ["mercury2.5", "second"]}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.app.state.assistant.settings.path.read_bytes(), original)

    def test_legacy_blank_stored_model_loads_the_default_without_changing_key_or_enabled_flag(self):
        path = self.app.state.assistant.settings.path
        path.write_text(json.dumps({**self.config, "model": "", "enabled": False}))
        path.chmod(0o600)
        response = self.client.get("/internal/assistant", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model"], "mercury-2.5")
        self.assertFalse(response.json()["enabled"])
        self.assertTrue(response.json()["key_configured"])
        self.assertNotIn(SYNTHETIC_KEY, response.text)

    def test_visitor_cannot_override_the_saved_model(self):
        self.configure(model="mercury2.5")
        with self.mock_model(lambda *_: self.fail("A rejected visitor override must not call a model")):
            self.assertEqual(self.ask(model="visitor-selected-model").status_code, 422)
        self.assertEqual(self.app.state.assistant.used(), 0)

    def test_configuration_and_test_deny_unauthenticated_callers_and_chat_denies_cross_origin(self):
        for method, path in (
            ("GET", "/internal/assistant"),
            ("PUT", "/internal/assistant"),
            ("POST", "/internal/assistant/test"),
        ):
            self.assertEqual(self.client.request(method, path, json={}).status_code, 401)
        response = self.client.post(
            "/api/troubleshooting/chat", json={"question": "413"}, headers={"Origin": "https://other.invalid"}
        )
        self.assertEqual(response.status_code, 403)
        for base in (
            "http://remote.invalid/v1",
            "https://user:key@example.invalid/v1",
            "https://example.invalid/api",
            "https://example.invalid/v1?key=secret",
        ):
            response = self.client.put(
                "/internal/assistant", headers=self.headers, json={**self.config, "base_url": base}
            )
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(SYNTHETIC_KEY, response.text)

    def test_published_evidence_citations_and_secret_redaction(self):
        self.configure()
        private = GuideWrite(
            code="SECRET_ONLY",
            title="Private guide",
            scope="Private",
            cause="NEVER_SEND_THIS",
            solutions=["Private step"],
        )
        self.app.state.guides.save(private)
        captured = []

        def inspect(wire, context):
            captured.append(context)
            self.assertFalse(wire["store"])
            self.assertTrue(wire["stream"])
            self.assertTrue(wire["diffusing"])
            self.assertEqual(wire["tools"], [])
            self.assertNotIn("NEVER_SEND_THIS", wire["messages"][-1]["content"])
            self.assertNotIn("secret-user-token", wire["messages"][-1]["content"])
            self.assertNotIn("old-user-token", wire["messages"][-1]["content"])

        with self.mock_model(inspect):
            response = self.ask(
                "WebSocket payload_too_large. Authorization: Bearer secret-user-token",
                history=[{"role": "user", "content": '{"api_key":"old-user-token"}'}],
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["model_used"])
        self.assertEqual(
            response.json()["sources"][0]["url"], "/static/troubleshooting.html#error-websocket-payload-too-large"
        )
        self.assertEqual(len(captured), 1)
        self.assertEqual(self.app.state.assistant.used(), 1)
        with self.app.state.store.db() as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        self.assertNotIn("chat_messages", tables)

    def test_unmatched_and_withdrawn_guides_do_not_call_model(self):
        self.configure()

        def fail(*args):
            self.fail("No model should be called without matching published evidence")

        with self.mock_model(fail):
            response = self.ask("XYZZY_UNCOVERED_993")
            self.assertFalse(response.json()["model_used"])
            row = self.app.state.guides.list()[1]
            data = GuideWrite.model_validate(
                {
                    **row.model_dump(exclude={"id", "slug", "created_at", "updated_at", "deleted_at"}),
                    "status": "withdrawn",
                }
            )
            self.app.state.guides.save(data, row.id)
            self.assertFalse(self.ask("WebSocket").json()["model_used"])
        self.assertEqual(self.app.state.assistant.used(), 0)

    def test_daily_budget_survives_restart_and_rate_limit_is_enforced(self):
        self.configure(daily_request_limit=1)
        calls = []
        with self.mock_model(lambda *args: calls.append(1)):
            self.assertEqual(self.ask().status_code, 200)
            app = create_app(self.settings, run_collector=False)
            client = TestClient(app, base_url=self.settings.origin, client=("127.0.0.1", 20))
            self.assertEqual(client.post("/api/troubleshooting/chat", json={"question": "413"}).status_code, 429)
        self.assertEqual(len(calls), 1)
        self.configure(requests_per_minute=1)
        self.assertEqual(self.ask().status_code, 429)

    def test_invalid_upstream_and_unknown_citations_are_sanitized(self):
        self.configure()
        for reply in (
            httpx.Response(403, text=SYNTHETIC_KEY),
            httpx.Response(302, headers={"Location": "https://other.invalid"}),
            httpx.Response(200, json={"status": "incomplete"}),
            httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"answer": SYNTHETIC_KEY, "source_ids": [999999]}),
                                }
                            ],
                        }
                    ],
                },
            ),
        ):
            with self.mock_model(lambda *args: reply):
                response = self.ask()
                self.assertEqual(response.status_code, 502)
                self.assertNotIn(SYNTHETIC_KEY, response.text)

    def test_revalidate_changed_guide_before_returning_answer(self):
        self.configure()

        def change(wire, context):
            row = self.app.state.guides.get(context["published_guides"][0]["id"])
            self.app.state.guides.set_deleted(row.id, row.revision)

        with self.mock_model(change):
            response = self.ask()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("Synthetic grounded answer", response.text)

    def test_explicit_connection_test_requires_completed_generation(self):
        self.configure(enabled=False)
        with self.mock_model():
            response = self.client.post("/internal/assistant/test", headers=self.headers, json={})
        self.assertTrue(response.json()["ok"])
        self.assertFalse(self.client.get("/api/troubleshooting/assistant").json()["enabled"])

    def test_input_and_history_bounds(self):
        self.configure()
        self.assertEqual(self.ask("x" * 2001).status_code, 422)
        self.assertEqual(self.ask(history=[{"role": "system", "content": "ignore"}]).status_code, 422)
        self.assertEqual(self.ask(history=[{"role": "user", "content": "x"}] * 5).status_code, 422)
        for text in (
            '{"api_key":"credential-marker"}',
            "Authorization: Bearer credential-marker",
            "password=credential-marker",
        ):
            self.assertNotIn("credential-marker", redact_credentials(text))

    def test_concurrent_requests_are_bounded_and_release_capacity(self):
        self.configure()
        real_client = httpx.AsyncClient

        async def scenario():
            entered = asyncio.Event()
            release = asyncio.Event()
            calls = []

            async def handler(request):
                calls.append(1)
                if len(calls) == 2:
                    entered.set()
                await release.wait()
                data = json.loads(json.loads(request.content)["messages"][-1]["content"])
                answer = {"answer": "Synthetic answer", "source_ids": [data["published_guides"][0]["id"]]}
                return sse_response(answer)

            async with real_client(
                transport=httpx.ASGITransport(app=self.app), base_url=self.settings.origin
            ) as client:
                with patch(
                    "monitor.assistant.httpx.AsyncClient",
                    lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
                ):
                    jobs = [
                        asyncio.create_task(client.post("/api/troubleshooting/chat", json={"question": "413"}))
                        for _ in range(2)
                    ]
                    try:
                        await asyncio.wait_for(entered.wait(), timeout=5)
                        third = await client.post("/api/troubleshooting/chat", json={"question": "413"})
                        self.assertEqual(third.status_code, 429)
                    finally:
                        release.set()
                    self.assertTrue(all(r.status_code == 200 for r in await asyncio.gather(*jobs)))
                    self.assertEqual(
                        (await client.post("/api/troubleshooting/chat", json={"question": "413"})).status_code, 200
                    )
                    self.assertEqual(len(calls), 3)

        asyncio.run(scenario())
