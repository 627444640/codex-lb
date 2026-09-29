from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize("method,suffix", [("GET", ""), ("PUT", ""), ("POST", "/test")])
async def test_retired_assistant_admin_routes_are_unavailable(async_client, app_instance, monkeypatch, method, suffix):
    from app.modules.status_page.service import StatusPageService

    outbound = AsyncMock(side_effect=AssertionError("Retired model routes must not call the monitor"))
    monkeypatch.setattr(StatusPageService, "_request", outbound)
    response = await async_client.request(method, "/api/settings/status-page/assistant" + suffix, json={})
    assert response.status_code in {404, 405}
    assert not any(path.startswith("/api/settings/status-page/assistant") for path in app_instance.openapi()["paths"])
    outbound.assert_not_awaited()
