from __future__ import annotations

import pytest

from app.core.config.settings_cache import get_settings_cache
from app.modules.dashboard_auth.service import DASHBOARD_SESSION_COOKIE, DashboardAuthService, _hash_password

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _cookie(response) -> dict[str, str]:
    return {"Cookie": f"{DASHBOARD_SESSION_COOKIE}={response.cookies[DASHBOARD_SESSION_COOKIE]}"}


async def test_password_rotation_rejects_every_cookie_consumer_and_new_login_succeeds(async_client):
    setup = await async_client.post("/api/dashboard-auth/password/setup", json={"password": "password123"})
    old_cookie = _cookie(setup)
    assert (await async_client.get("/api/settings", headers=old_cookie)).status_code == 200
    changed = await async_client.post(
        "/api/dashboard-auth/password/change",
        headers=old_cookie,
        json={"currentPassword": "password123", "newPassword": "new-password123"},
    )
    assert changed.status_code == 200
    assert (await async_client.get("/api/settings", headers=old_cookie)).status_code == 401
    status = (await async_client.get("/api/dashboard-auth/session", headers=old_cookie)).json()
    assert status["authenticated"] is False
    assert status["passwordSessionActive"] is False
    for endpoint, body in (
        ("password/change", {"currentPassword": "new-password123", "newPassword": "another-password"}),
        ("totp/setup/start", {}),
        ("totp/setup/confirm", {"secret": "JBSWY3DPEHPK3PXP", "code": "123456"}),
        ("totp/verify", {"code": "123456"}),
        ("totp/disable", {"code": "123456"}),
    ):
        rejected = await async_client.post(f"/api/dashboard-auth/{endpoint}", headers=old_cookie, json=body)
        assert rejected.status_code == 401, (endpoint, rejected.text)
    removed = await async_client.request(
        "DELETE", "/api/dashboard-auth/password", headers=old_cookie, json={"password": "new-password123"}
    )
    assert removed.status_code == 401
    login = await async_client.post("/api/dashboard-auth/password/login", json={"password": "new-password123"})
    assert login.status_code == 200
    assert (await async_client.get("/api/settings", headers=_cookie(login))).status_code == 200


async def test_guest_rotation_preserves_admin_and_unrelated_settings_preserve_sessions(async_client):
    admin = await async_client.post("/api/dashboard-auth/password/setup", json={"password": "password123"})
    admin_cookie = _cookie(admin)
    settings = {
        "stickyThreadsEnabled": False,
        "preferEarlierResetAccounts": False,
        "totpRequiredOnLogin": False,
        "apiKeyAuthEnabled": False,
        "guestAccessEnabled": True,
    }
    assert (await async_client.put("/api/settings", headers=admin_cookie, json=settings)).status_code == 200
    assert (
        await async_client.post(
            "/api/dashboard-auth/guest/password", headers=admin_cookie, json={"password": "guest-password"}
        )
    ).status_code == 200
    guest = await async_client.post("/api/dashboard-auth/guest/login", json={"password": "guest-password"})
    guest_cookie = _cookie(guest)
    assert (await async_client.get("/api/settings", headers=guest_cookie)).status_code == 200
    settings["stickyThreadsEnabled"] = True
    assert (await async_client.put("/api/settings", headers=admin_cookie, json=settings)).status_code == 200
    assert (await async_client.get("/api/settings", headers=guest_cookie)).status_code == 200
    assert (
        await async_client.post(
            "/api/dashboard-auth/guest/password", headers=admin_cookie, json={"password": "rotated-guest-password"}
        )
    ).status_code == 200
    assert (await async_client.get("/api/settings", headers=guest_cookie)).status_code == 401
    assert (await async_client.get("/api/settings", headers=admin_cookie)).status_code == 200
    login = await async_client.post("/api/dashboard-auth/guest/login", json={"password": "rotated-guest-password"})
    assert (await async_client.get("/api/settings", headers=_cookie(login))).status_code == 200


async def test_login_rotation_race_never_mints_a_cookie_for_unverified_credentials(async_client, monkeypatch):
    await async_client.post("/api/dashboard-auth/password/setup", json={"password": "password123"})
    verify = DashboardAuthService.verify_password
    rotated_hash = _hash_password("new-password123")

    async def rotate_after_verification(self, password, *, actor_ip=None):
        fingerprint = await verify(self, password, actor_ip=actor_ip)
        # Rotate after bcrypt succeeded but before the route issues the cookie.
        await self._repository.set_password_hash(rotated_hash)
        await get_settings_cache().invalidate()
        return fingerprint

    monkeypatch.setattr(DashboardAuthService, "verify_password", rotate_after_verification)
    login = await async_client.post("/api/dashboard-auth/password/login", json={"password": "password123"})
    assert login.status_code == 200
    old_cookie = _cookie(login)
    assert login.json()["authenticated"] is False
    assert login.json()["passwordSessionActive"] is False
    assert (await async_client.get("/api/settings", headers=old_cookie)).status_code == 401
    monkeypatch.setattr(DashboardAuthService, "verify_password", verify)
    fresh = await async_client.post("/api/dashboard-auth/password/login", json={"password": "new-password123"})
    assert (await async_client.get("/api/settings", headers=_cookie(fresh))).status_code == 200
