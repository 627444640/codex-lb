from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import StatusPageContext, get_status_page_context
from app.modules.status_page.guide_schemas import GuideListResponse, GuideRecord
from app.modules.status_page.service import (
    StatusPageContentConflict,
    StatusPageContentNotFound,
    StatusPageService,
    StatusPageUnavailable,
)

pytestmark = pytest.mark.integration

DATA = {
    "code": "WS",
    "title": "WebSocket size",
    "scope": "Synthetic symptom",
    "cause": "Synthetic cause",
    "solutions": ["Reduce the image"],
    "status": "draft",
    "sortOrder": 20,
}


@pytest.fixture
def guide_service(app_instance):
    service = StatusPageService(Path("/missing-test-connector"))
    row = GuideRecord.model_validate(
        {
            **DATA,
            "id": 7,
            "slug": "error-synthetic",
            "revision": 3,
            "createdAt": datetime(2026, 9, 28, tzinfo=timezone.utc),
            "updatedAt": datetime(2026, 9, 28, tzinfo=timezone.utc),
            "deletedAt": None,
        }
    )
    service.list_guides = AsyncMock(return_value=GuideListResponse(available=True, guides=[row]))
    service.save_guide = AsyncMock(return_value=row)
    service.delete_guide = AsyncMock(return_value=row)
    app_instance.dependency_overrides[get_status_page_context] = lambda: StatusPageContext(service=service)
    yield service
    app_instance.dependency_overrides.pop(get_status_page_context, None)


async def initialize(client):
    assert (
        await client.post("/api/dashboard-auth/password/setup", json={"password": "isolated-guide-test"})
    ).status_code == 200


@pytest.mark.asyncio
async def test_guide_crud_uses_admin_session_and_revision(async_client, guide_service):
    await initialize(async_client)
    base = "/api/settings/status-page/guides"
    response = await async_client.get(base)
    assert response.status_code == 200
    assert response.json()["guides"][0]["sortOrder"] == 20
    assert response.json()["guides"][0]["deletedAt"] is None
    assert (await async_client.post(base, json=DATA)).status_code == 201
    assert (await async_client.put(f"{base}/7", json={**DATA, "revision": 3})).status_code == 200
    assert guide_service.save_guide.await_args.args[0].revision == 3
    assert guide_service.save_guide.await_args.args[1] == 7
    assert (await async_client.request("DELETE", f"{base}/7", json={"revision": 3})).status_code == 200
    assert (await async_client.post(f"{base}/7/restore", json={"revision": 4})).status_code == 200
    assert guide_service.delete_guide.await_args.kwargs == {"restore": True}


@pytest.mark.asyncio
async def test_guide_reads_and_every_mutation_deny_guests_and_remote_anonymous(
    async_client, app_instance, guide_service
):
    await initialize(async_client)
    paths = [("GET", ""), ("POST", ""), ("PUT", "/7"), ("DELETE", "/7"), ("POST", "/7/restore")]
    async with AsyncClient(
        transport=ASGITransport(app=app_instance, client=("203.0.113.4", 1234)), base_url="http://testserver"
    ) as remote:
        for method, suffix in paths:
            assert (
                await remote.request(method, "/api/settings/status-page/guides" + suffix, json={})
            ).status_code == 401
        assert (await async_client.put("/api/settings", json={"guestAccessEnabled": True})).status_code == 200
        for method, suffix in paths:
            assert (
                await remote.request(method, "/api/settings/status-page/guides" + suffix, json={})
            ).status_code == 403
    guide_service.list_guides.assert_not_awaited()
    guide_service.save_guide.assert_not_awaited()
    guide_service.delete_guide.assert_not_awaited()


@pytest.mark.asyncio
async def test_guide_origin_validation_and_conflict(async_client, guide_service):
    await initialize(async_client)
    base = "/api/settings/status-page/guides"
    for method, suffix in (("POST", ""), ("PUT", "/7"), ("DELETE", "/7"), ("POST", "/7/restore")):
        assert (
            await async_client.request(method, base + suffix, json={}, headers={"Origin": "https://other.invalid"})
        ).status_code == 403
    assert (await async_client.post(base, json={**DATA, "endpointUrl": "javascript:alert(1)"})).status_code == 422
    assert (await async_client.post(base, json={**DATA, "solutions": ["  "]})).status_code == 422
    guide_service.save_guide.side_effect = StatusPageContentConflict()
    response = await async_client.put(f"{base}/7", json={**DATA, "revision": 2})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "status_page_content_conflict"


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [(StatusPageUnavailable(), 503), (StatusPageContentNotFound(), 404)])
async def test_control_errors_use_dashboard_envelopes(async_client, guide_service, error, status):
    await initialize(async_client)
    guide_service.list_guides.side_effect = error
    response = await async_client.get("/api/settings/status-page/guides")
    assert response.status_code == status
    assert response.json()["error"]["code"] == error.code
