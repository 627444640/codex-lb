from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.utils.time import utcnow
from app.db.models import ApiKeyLimit, ApiKeyUsageReservation, LimitType, LimitWindow
from app.db.session import SessionLocal
from app.modules.api_keys.repository import ApiKeysRepository
from app.modules.api_keys.service import ApiKeyInvalidError, ApiKeysService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_credits_create_and_update_are_rejected_atomically(async_client):
    unsupported = {"limitType": "credits", "limitWindow": "daily", "maxValue": 1}
    rejected = await async_client.post("/api/api-keys/", json={"name": "unsupported", "limits": [unsupported]})
    assert rejected.status_code == 400
    assert "unsupported" in rejected.json()["error"]["message"]
    assert (await async_client.get("/api/api-keys/")).json() == []

    supported = {"limitType": "total_tokens", "limitWindow": "daily", "maxValue": 1000}
    created = await async_client.post("/api/api-keys/", json={"name": "supported", "limits": [supported]})
    assert created.status_code == 200
    key_id = created.json()["id"]
    rejected = await async_client.patch(
        f"/api/api-keys/{key_id}", json={"name": "must-not-change", "limits": [supported, unsupported]}
    )
    assert rejected.status_code == 400
    [unchanged] = (await async_client.get("/api/api-keys/")).json()
    assert unchanged["name"] == "supported"
    assert [limit["limitType"] for limit in unchanged["limits"]] == ["total_tokens"]


@pytest.mark.parametrize("expired", [False, True])
async def test_legacy_credits_blocks_auth_and_admission_until_replaced(async_client, expired):
    settings = await async_client.put(
        "/api/settings",
        json={
            "stickyThreadsEnabled": False,
            "preferEarlierResetAccounts": False,
            "totpRequiredOnLogin": False,
            "apiKeyAuthEnabled": True,
        },
    )
    assert settings.status_code == 200
    created = (await async_client.post("/api/api-keys/", json={"name": "legacy"})).json()
    key_id = created["id"]
    async with SessionLocal() as session:
        session.add(
            ApiKeyLimit(
                api_key_id=key_id,
                limit_type=LimitType.CREDITS,
                limit_window=LimitWindow.DAILY,
                max_value=1,
                current_value=0,
                reset_at=utcnow() + timedelta(days=-1 if expired else 1),
            )
        )
        await session.commit()
    headers = {"Authorization": f"Bearer {created['key']}"}
    for endpoint in ("/v1/responses", "/backend-api/codex/responses"):
        rejected = await async_client.post(endpoint, headers=headers, json={"model": "gpt-5", "input": "test"})
        assert rejected.status_code == 401
        assert "unsupported credits limit" in rejected.json()["error"]["message"]
    async with SessionLocal() as session:
        with pytest.raises(ApiKeyInvalidError, match="unsupported credits"):
            await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(key_id, request_model="gpt-5")
        assert await session.scalar(select(func.count()).select_from(ApiKeyUsageReservation)) == 0

    listed = (await async_client.get("/api/api-keys/")).json()
    assert listed[0]["limits"][0]["limitType"] == "credits"
    replaced = await async_client.patch(
        f"/api/api-keys/{key_id}",
        json={"limits": [{"limitType": "cost_usd", "limitWindow": "daily", "maxValue": 1000000}]},
    )
    assert replaced.status_code == 200
    assert (await async_client.get("/v1/models", headers=headers)).status_code == 200
