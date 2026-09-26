from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import aiohttp
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config.settings import Settings, get_settings
from app.db.models import DashboardSettings
from app.db.session import SessionLocal
from app.modules.settings.repository import SettingsRepository

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_enabled", [None, "false", "true"])
@pytest.mark.parametrize("persisted_consent", ["undecided", "disabled", "enabled"])
async def test_retired_telemetry_cannot_be_reactivated_and_preserves_settings(
    app_instance,
    monkeypatch: pytest.MonkeyPatch,
    legacy_enabled: str | None,
    persisted_consent: str,
) -> None:
    if legacy_enabled is None:
        monkeypatch.delenv("CODEX_LB_TELEMETRY_ENABLED", raising=False)
    else:
        monkeypatch.setenv("CODEX_LB_TELEMETRY_ENABLED", legacy_enabled)
    monkeypatch.setenv("CODEX_LB_TELEMETRY_ENDPOINT", "https://collector.example.invalid")
    get_settings.cache_clear()

    assert "telemetry_enabled" not in Settings.model_fields
    assert "telemetry_endpoint" not in Settings.model_fields
    assert not any(name.startswith("telemetry_") for name in get_settings().model_dump())
    assert "/api/settings/telemetry" not in app_instance.openapi()["paths"]

    # These deliberately synthetic legacy values must stay inert. In
    # particular, startup must never try to decrypt or replace the identity.
    legacy_identity = "00000000-0000-4000-8000-000000000001"
    legacy_key = b"inert-legacy-test-ciphertext"
    async with SessionLocal() as session:
        row = await SettingsRepository(session).get_or_create()
        row.telemetry_consent = persisted_consent
        row.telemetry_instance_id = legacy_identity
        row.telemetry_private_key_encrypted = legacy_key
        await session.commit()

    outbound_request = AsyncMock(side_effect=AssertionError("unexpected outbound HTTP request"))
    monkeypatch.setattr(aiohttp.ClientSession, "_request", outbound_request)

    async with app_instance.router.lifespan_context(app_instance):
        await asyncio.sleep(0)
        assert not any(task.get_name().startswith("anonymous-telemetry") for task in asyncio.all_tasks())

        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            for path in (
                "/api/settings/telemetry",
                "/api/settings/telemetry/",
                "/api/settings/telemetry?include_preview=true",
            ):
                response = await client.get(path)
                assert response.status_code == 404

            # The generic GET-only SPA fallback naturally gives an unsupported
            # write method 405 after the telemetry router is removed.
            for path in ("/api/settings/telemetry", "/api/settings/telemetry/"):
                for enabled in (False, True):
                    response = await client.put(path, json={"enabled": enabled})
                    assert response.status_code == 405

            response = await client.get("/api/settings")
            assert response.status_code == 200
            assert response.json()["stickyThreadsEnabled"] is True

            response = await client.put("/api/settings", json={"stickyThreadsEnabled": False})
            assert response.status_code == 200
            assert response.json()["stickyThreadsEnabled"] is False

            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"

    # Also inspect after lifespan shutdown, so a swallowed sender failure or
    # shutdown opt-out attempt cannot make the test pass accidentally.
    outbound_request.assert_not_called()
    assert not any(task.get_name().startswith("anonymous-telemetry") for task in asyncio.all_tasks())
    async with SessionLocal() as session:
        row = await session.get(DashboardSettings, 1)
        assert row is not None
        assert row.sticky_threads_enabled is False
        assert row.telemetry_consent == persisted_consent
        assert row.telemetry_instance_id == legacy_identity
        assert row.telemetry_private_key_encrypted == legacy_key
