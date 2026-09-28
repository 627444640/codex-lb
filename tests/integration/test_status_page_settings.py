from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import StatusPageContext, get_status_page_context
from app.modules.status_page.schemas import AnnouncementSaved, EmailConfigurationResponse, StatusPageSettingsResponse
from app.modules.status_page.service import StatusPageService

pytestmark = pytest.mark.integration


@pytest.fixture
def status_service(app_instance):
    service = StatusPageService(Path("/nonexistent-test-connector"))
    email = EmailConfigurationResponse(
        enabled=False,
        host="smtp.example.invalid",
        port=465,
        tls="ssl",
        sender="sender@example.invalid",
        username="sender@example.invalid",
        recipients=["recipient@example.invalid"],
        password_configured=True,
    )
    service.get_settings = AsyncMock(return_value=StatusPageSettingsResponse(available=True, email=email))
    service.update_email = AsyncMock(return_value=email)
    service.save_announcement = AsyncMock(return_value=AnnouncementSaved(id=12))
    app_instance.dependency_overrides[get_status_page_context] = lambda: StatusPageContext(service=service)
    yield service
    app_instance.dependency_overrides.pop(get_status_page_context, None)


async def initialize(client):
    response = await client.post("/api/dashboard-auth/password/setup", json={"password": "isolated-status-password"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_status_settings_reuses_admin_session_and_serializes_secret_safely(async_client, status_service):
    await initialize(async_client)
    response = await async_client.get("/api/settings/status-page")
    assert response.status_code == 200
    assert response.json()["email"]["passwordConfigured"] is True
    payload = {
        "enabled": True,
        "host": "smtp.example.invalid",
        "port": 465,
        "tls": "ssl",
        "sender": "sender@example.invalid",
        "username": "sender@example.invalid",
        "recipients": ["recipient@example.invalid"],
        "password": "never-return-this-secret",
    }
    response = await async_client.put("/api/settings/status-page/email", json=payload)
    assert response.status_code == 200
    assert "never-return-this-secret" not in response.text
    assert status_service.update_email.await_args.args[0].password.get_secret_value() == "never-return-this-secret"


@pytest.mark.asyncio
async def test_guest_and_remote_unauthenticated_cannot_read_or_write_control(
    async_client, app_instance, status_service
):
    await initialize(async_client)
    transport = ASGITransport(app=app_instance, client=("203.0.113.42", 1234))
    async with AsyncClient(transport=transport, base_url="http://testserver") as remote:
        assert (await remote.get("/api/settings/status-page")).status_code == 401
        assert (await remote.put("/api/settings/status-page/email", json={})).status_code == 401
        assert (await async_client.put("/api/settings", json={"guestAccessEnabled": True})).status_code == 200
        assert (await remote.get("/api/settings/status-page")).status_code == 403
        assert (await remote.post("/api/settings/status-page/announcements", json={})).status_code == 403
    status_service.get_settings.assert_not_awaited()
    status_service.update_email.assert_not_awaited()
    status_service.save_announcement.assert_not_awaited()


@pytest.mark.asyncio
async def test_announcement_routes_validate_schedule_and_origin(async_client, status_service):
    await initialize(async_client)
    payload = {
        "title": "Maintenance",
        "body": "Planned maintenance",
        "level": "maintenance",
        "status": "draft",
        "startsAt": "2026-09-28T10:00:00+08:00",
        "endsAt": "2026-09-28T11:00:00+08:00",
    }
    response = await async_client.post("/api/settings/status-page/announcements", json=payload)
    assert response.status_code == 201
    assert response.json() == {"id": 12}
    sent = status_service.save_announcement.await_args.args[0]
    assert sent.starts_at == datetime(2026, 9, 28, 2, tzinfo=timezone.utc)
    assert (
        await async_client.put("/api/settings/status-page/announcements/12", json={**payload, "status": "withdrawn"})
    ).status_code == 200
    assert (
        await async_client.put(
            "/api/settings/status-page/announcements/12", json={**payload, "endsAt": "2026-09-27T10:00:00Z"}
        )
    ).status_code == 422
    assert (
        await async_client.post(
            "/api/settings/status-page/announcements", json=payload, headers={"Origin": "https://evil.invalid"}
        )
    ).status_code == 403
