from __future__ import annotations

import unittest
from pathlib import Path

from monitor.config import OfficialStatusSettings, Settings
from monitor.official_status import fetch, normalize

PAYLOAD = {
    "page": {"updated_at": "2026-10-13T09:30:00Z"},
    "status": {"indicator": "minor", "description": "Partial System Degradation"},
    "components": [
        {"id": "component-1", "name": "Responses", "status": "operational"},
        {"id": "component-2", "name": "Chat Completions", "status": "degraded_performance"},
        {"id": "bad id", "name": "Ignored", "status": "major_outage"},
    ],
    "incidents": [
        {
            "id": "incident-1",
            "name": "Elevated errors",
            "status": "monitoring",
            "impact": "minor",
            "created_at": "2026-10-13T08:10:00Z",
            "updated_at": "2026-10-13T09:30:00Z",
        }
    ],
}


class FakeResponse:
    def __init__(self, payload, status_code=200, content_type="application/json"):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.content = b"{}"
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_bytes(self):
        import json

        yield json.dumps(self._payload).encode()


class FakeClient:
    response = None
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def stream(self, method, url, headers):
        self.calls.append((url, headers, self.kwargs))
        return self.response


class OfficialStatusTests(unittest.TestCase):
    def setUp(self):
        FakeClient.calls = []
        self.settings = OfficialStatusSettings(enabled=True)

    def test_normalize_maps_provider_state_and_bounds_public_fields(self):
        result = normalize(PAYLOAD, self.settings, 1791883860)

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["indicator"], "minor")
        self.assertEqual(len(result["components"]), 2)
        self.assertEqual(result["incidents"][0]["status"], "monitoring")
        self.assertEqual(result["incidents"][0]["url"], "https://status.openai.com/incidents/incident-1")
        self.assertNotIn("incident_updates", result["incidents"][0])

    def test_normalize_requires_provider_page_timestamp_and_omits_resolved_incidents(self):
        payload = {
            **PAYLOAD,
            "page": {},
            "incidents": [
                {"id": "resolved-1", "name": "Resolved", "status": "resolved", "impact": "minor"},
                *PAYLOAD["incidents"],
            ],
        }
        result = normalize(payload, self.settings, 1791883860)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["stale"])

        payload["page"] = PAYLOAD["page"]
        result = normalize(payload, self.settings, 1791883860)
        self.assertEqual([incident["id"] for incident in result["incidents"]], ["incident-1"])

    def test_disabled_status_does_not_make_request(self):
        result = fetch(OfficialStatusSettings(), 1791883860, FakeClient)
        self.assertIsNone(result)
        self.assertEqual(FakeClient.calls, [])

    def test_config_rejects_non_boolean_enable_flag(self):
        with self.assertRaises(ValueError):
            Settings(
                source_db=Path("/tmp/codex-lb-source.db"),
                state_dir=Path("/tmp/codex-lb-monitor"),
                checks=(),
                official_status=OfficialStatusSettings(enabled="false"),
            ).validate()

    def test_fetch_uses_bounded_json_request(self):
        FakeClient.response = FakeResponse(PAYLOAD)
        result = fetch(self.settings, 1791883860, FakeClient)

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(FakeClient.calls[0][0], self.settings.url)
        self.assertEqual(FakeClient.calls[0][1], {"Accept": "application/json"})
        self.assertEqual(FakeClient.calls[0][2], {"timeout": 2, "follow_redirects": False, "trust_env": False})

    def test_fetch_hides_transport_schema_and_content_type_failures(self):
        for response in (
            FakeResponse(PAYLOAD, status_code=503),
            FakeResponse({}, content_type="text/html"),
            FakeResponse({"status": {"indicator": "minor"}}),
        ):
            with self.subTest(response=response):
                FakeClient.response = response
                result = fetch(self.settings, 1791883860, FakeClient)
                self.assertEqual(result["status"], "unknown")
                self.assertTrue(result["stale"])
                self.assertEqual(result["incidents"], [])

    def test_fetch_stops_before_retaining_an_oversized_stream(self):
        class OversizedResponse(FakeResponse):
            def iter_bytes(self):
                yield b"x" * (1024 * 1024 + 1)

        FakeClient.response = OversizedResponse(PAYLOAD)
        result = fetch(self.settings, 1791883860, FakeClient)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["stale"])

    def test_unknown_indicator_does_not_become_outage(self):
        payload = {**PAYLOAD, "status": {"indicator": "future_state", "description": "Unknown"}}
        result = normalize(payload, self.settings, 1791883860)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["indicator"])
