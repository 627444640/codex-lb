from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config.settings import get_settings
from app.db.models import DashboardSettings
from app.db.session import SessionLocal

pytestmark = pytest.mark.integration
PASSWORD = "isolated-admin-password"


@pytest.fixture
def managed_policy(monkeypatch):
    monkeypatch.setenv("CODEX_LB_DEPLOYMENT_AUTH_POLICY", "managed")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def auth_snapshot():
    async with SessionLocal() as session:
        row = await session.get(DashboardSettings, 1)
        return (
            row.password_hash,
            row.guest_password_hash,
            row.totp_secret_encrypted,
            row.api_key_auth_enabled,
            row.guest_access_enabled,
            row.version,
            row.sticky_threads_enabled,
        )


async def initialize(client):
    response = await client.post("/api/dashboard-auth/password/setup", json={"password": PASSWORD})
    assert response.status_code == 200
    response = await client.put("/api/settings", json={"apiKeyAuthEnabled": True})
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_managed_rejects_destructive_writes_atomically(async_client, managed_policy):
    settings = await initialize(async_client)
    assert settings["deploymentAuthPolicy"] == {
        "mode": "managed",
        "adminPasswordRequired": True,
        "apiKeyAuthRequired": True,
        "guestPassword": "optional",
    }
    async with SessionLocal() as session:
        row = await session.get(DashboardSettings, 1)
        row.totp_secret_encrypted = b"isolated-preservation-sentinel"
        await session.commit()
    before = await auth_snapshot()
    response = await async_client.put(
        "/api/settings",
        json={
            "apiKeyAuthEnabled": False,
            "guestAccessEnabled": True,
            "stickyThreadsEnabled": not settings["stickyThreadsEnabled"],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "deployment_policy_violation"
    assert response.json()["error"]["param"] == "apiKeyAuthEnabled"
    assert await auth_snapshot() == before
    response = await async_client.request("DELETE", "/api/dashboard-auth/password", json={"password": PASSWORD})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "deployment_policy_violation"
    assert await auth_snapshot() == before


@pytest.mark.asyncio
async def test_managed_stale_settings_cannot_overwrite_guest_or_policy(async_client, managed_policy):
    settings = await initialize(async_client)
    assert (await async_client.put("/api/settings", json={"guestAccessEnabled": True})).status_code == 200
    before = await auth_snapshot()
    response = await async_client.put(
        "/api/settings",
        json={"expectedVersion": settings["version"], "guestAccessEnabled": False, "apiKeyAuthEnabled": True},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "settings_conflict"
    assert await auth_snapshot() == before
    assert (await async_client.get("/api/dashboard-auth/session")).json()["role"] == "admin"
    forged = await async_client.put("/api/settings", json={"deploymentAuthPolicy": {"mode": "standard"}})
    assert forged.status_code == 422
    assert await auth_snapshot() == before


@pytest.mark.asyncio
async def test_managed_guest_lifecycle_keeps_auth_boundaries(async_client, app_instance, managed_policy):
    await initialize(async_client)
    key_response = await async_client.post("/api/api-keys/", json={"name": "isolated-policy-test"})
    assert key_response.status_code == 200
    key = key_response.json()["key"]
    transport = ASGITransport(app=app_instance, client=("203.0.113.21", 50001))
    async with AsyncClient(transport=transport, base_url="http://testserver") as guest:
        for password in (None, "isolated-guest-first", "isolated-guest-second", None):
            response = await async_client.put("/api/settings", json={"guestAccessEnabled": True})
            assert response.status_code == 200
            if password:
                response = await async_client.post("/api/dashboard-auth/guest/password", json={"password": password})
            else:
                response = await async_client.delete("/api/dashboard-auth/guest/password")
            assert response.status_code == 200
            guest.cookies.clear()
            if password:
                assert (await guest.get("/api/settings")).status_code == 401
            response = await guest.post("/api/dashboard-auth/guest/login", json={"password": password})
            assert response.status_code == 200
            assert response.json()["permissions"] == ["read"]
            assert (await guest.get("/api/settings")).status_code == 200
            assert (await guest.put("/api/settings", json={"guestAccessEnabled": False})).status_code == 403
            assert (await guest.get("/api/conversations")).status_code == 403
            assert (await guest.get("/v1/models")).status_code == 401
            assert (
                await guest.get("/v1/models", headers={"Authorization": "Bearer invalid-policy-test"})
            ).status_code == 401
            assert (await guest.get("/v1/usage", headers={"Authorization": f"Bearer {key}"})).status_code == 200
        assert (await async_client.put("/api/settings", json={"guestAccessEnabled": False})).status_code == 200
        assert (await guest.get("/api/settings")).status_code == 401
    assert (
        await async_client.post(
            "/api/dashboard-auth/password/change",
            json={"currentPassword": PASSWORD, "newPassword": "isolated-changed-password"},
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_managed_bootstrap_can_repair_incrementally(async_client, managed_policy):
    # API-key protection can be enabled before the first administrator password.
    response = await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})
    assert response.status_code == 200
    assert (
        await async_client.post("/api/dashboard-auth/password/setup", json={"password": PASSWORD})
    ).status_code == 200
