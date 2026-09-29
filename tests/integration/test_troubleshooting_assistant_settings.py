from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import StatusPageContext, get_status_page_context
from app.modules.status_page.assistant_schemas import AssistantConfigurationResponse, AssistantConnectionTest
from app.modules.status_page.service import StatusPageService

pytestmark = pytest.mark.integration


@pytest.fixture
def assistant_service(app_instance):
    service = StatusPageService(Path("/missing-test-connector"))
    result = AssistantConfigurationResponse(model="synthetic-model", key_configured=True)
    service.get_assistant_configuration = AsyncMock(return_value=result)
    service.update_assistant_configuration = AsyncMock(return_value=result)
    service.test_assistant_connection = AsyncMock(
        return_value=AssistantConnectionTest(ok=True, message="Synthetic test")
    )
    app_instance.dependency_overrides[get_status_page_context] = lambda: StatusPageContext(service=service)
    yield service
    app_instance.dependency_overrides.pop(get_status_page_context, None)


async def initialize(client):
    response = await client.post("/api/dashboard-auth/password/setup", json={"password": "isolated-assistant-test"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_model_configuration_is_write_only_and_test_is_explicit(async_client, assistant_service):
    await initialize(async_client)
    base = "/api/settings/status-page/assistant"
    response = await async_client.get(base)
    assert response.json()["keyConfigured"] is True
    assert "apiKey" not in response.json()
    assistant_service.test_assistant_connection.assert_not_awaited()
    response = await async_client.put(
        base, json={"enabled": True, "model": "synthetic-model", "apiKey": "synthetic-private-value-only"}
    )
    assert response.status_code == 200
    assert "synthetic-private-value-only" not in response.text
    assert (
        assistant_service.update_assistant_configuration.await_args.args[0].api_key.get_secret_value()
        == "synthetic-private-value-only"
    )
    assistant_service.test_assistant_connection.assert_not_awaited()
    assert (await async_client.post(base + "/test", json={})).json()["ok"] is True
    assistant_service.test_assistant_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_configuration_and_test_require_admin(async_client, app_instance, assistant_service):
    await initialize(async_client)
    async with AsyncClient(
        transport=ASGITransport(app=app_instance, client=("203.0.113.4", 10)), base_url="http://testserver"
    ) as remote:
        for method, suffix in (("GET", ""), ("PUT", ""), ("POST", "/test")):
            assert (
                await remote.request(method, "/api/settings/status-page/assistant" + suffix, json={})
            ).status_code == 401
        await async_client.put("/api/settings", json={"guestAccessEnabled": True})
        for method, suffix in (("GET", ""), ("PUT", ""), ("POST", "/test")):
            assert (
                await remote.request(method, "/api/settings/status-page/assistant" + suffix, json={})
            ).status_code == 403
    assistant_service.get_assistant_configuration.assert_not_awaited()
    assistant_service.update_assistant_configuration.assert_not_awaited()
    assistant_service.test_assistant_connection.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_control_rejects_cross_origin_and_bad_destinations(async_client, assistant_service):
    await initialize(async_client)
    base = "/api/settings/status-page/assistant"
    assert (
        await async_client.post(base + "/test", json={}, headers={"Origin": "https://other.invalid"})
    ).status_code == 403
    assert (await async_client.put(base, json={}, headers={"Origin": "https://other.invalid"})).status_code == 403
    for url in (
        "http://example.invalid/v1",
        "https://user:key@example.invalid/v1",
        "https://example.invalid/v1?key=value",
    ):
        assert (await async_client.put(base, json={"baseUrl": url})).status_code == 422


@pytest.mark.asyncio
async def test_default_model_and_single_replacement_reach_the_private_control_api(async_client, assistant_service):
    await initialize(async_client)
    base = "/api/settings/status-page/assistant"
    response = await async_client.put(base, json={"enabled": False})
    assert response.status_code == 200
    assert assistant_service.update_assistant_configuration.await_args.args[0].model == "mercury-2.5"
    response = await async_client.put(base, json={"enabled": False, "model": " provider/replacement-v2:latest "})
    assert response.status_code == 200
    assert assistant_service.update_assistant_configuration.await_args.args[0].model == "provider/replacement-v2:latest"
    assistant_service.test_assistant_connection.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model",
    [
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
    ],
)
async def test_model_control_rejects_invalid_or_multiple_models_before_saving(async_client, assistant_service, model):
    await initialize(async_client)
    response = await async_client.put("/api/settings/status-page/assistant", json={"enabled": False, "model": model})
    assert response.status_code == 422
    assistant_service.update_assistant_configuration.assert_not_awaited()
    assistant_service.test_assistant_connection.assert_not_awaited()
