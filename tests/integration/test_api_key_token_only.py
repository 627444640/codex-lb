from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.usage.pricing import UsageCostBreakdown
from app.core.utils.time import utcnow
from app.db.models import ApiKeyLimit, ApiKeyUsageReservation, ApiKeyUsageReservationItem, LimitType, LimitWindow
from app.db.session import SessionLocal
from app.modules.api_keys.repository import TOKEN_LIMIT_TYPES, ApiKeysRepository
from app.modules.api_keys.service import (
    ApiKeyRateLimitExceededError,
    ApiKeyRequestPricing,
    ApiKeyRequestUsageBudget,
    ApiKeysService,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _create_token_key(client):
    response = await client.post(
        "/api/api-keys/",
        json={
            "name": "token-only",
            "limits": [{"limitType": "total_tokens", "limitWindow": "daily", "maxValue": 1000}],
        },
    )
    assert response.status_code == 200
    return response.json()


async def _seed_legacy_limits(key_id: str, *, expired: bool = True):
    async with SessionLocal() as session:
        for limit_type, current in ((LimitType.COST_USD, 37), (LimitType.CREDITS, 41)):
            session.add(
                ApiKeyLimit(
                    api_key_id=key_id,
                    limit_type=limit_type,
                    limit_window=LimitWindow.DAILY,
                    max_value=1,
                    current_value=current,
                    reset_at=utcnow() + timedelta(days=-1 if expired else 1),
                )
            )
        await session.commit()
        return await _legacy_snapshot(session, key_id)


async def _legacy_snapshot(session, key_id: str):
    result = await session.execute(
        select(ApiKeyLimit.__table__)
        .where(ApiKeyLimit.api_key_id == key_id, ApiKeyLimit.limit_type.not_in(TOKEN_LIMIT_TYPES))
        .order_by(ApiKeyLimit.id)
    )
    return result.all()


@pytest.mark.parametrize("limit_type", ["cost_usd", "credits"])
async def test_new_monetary_rules_are_rejected_atomically(async_client, limit_type):
    unsupported = {"limitType": limit_type, "limitWindow": "daily", "maxValue": 1}
    rejected = await async_client.post("/api/api-keys/", json={"name": "unsupported", "limits": [unsupported]})
    assert rejected.status_code == 422
    assert (await async_client.get("/api/api-keys/")).json() == []

    created = await _create_token_key(async_client)
    rejected = await async_client.patch(
        f"/api/api-keys/{created['id']}", json={"name": "must-not-change", "limits": [unsupported]}
    )
    assert rejected.status_code == 422
    [unchanged] = (await async_client.get("/api/api-keys/")).json()
    assert unchanged["name"] == "token-only"
    assert [limit["limitType"] for limit in unchanged["limits"]] == ["total_tokens"]


@pytest.mark.parametrize("expired", [False, True])
async def test_legacy_money_limits_are_inert_while_token_usage_is_enforced(async_client, expired):
    created = await _create_token_key(async_client)
    key_id = created["id"]
    historical = await _seed_legacy_limits(key_id, expired=expired)

    async with SessionLocal() as session:
        repository = ApiKeysRepository(session)
        service = ApiKeysService(repository)
        assert (await service.validate_key(created["key"])).id == key_id
        reservation = await service.enforce_limits_for_request(
            key_id,
            request_model="private-model-without-prices",
            request_service_tier="ultrafast",
            request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=10, output_tokens=20),
            request_pricing=ApiKeyRequestPricing(),
        )
        assert reservation is not None
        reserved = await repository.get_usage_reservation(reservation.reservation_id)
        assert reserved is not None
        assert [(item.limit_type, item.reserved_delta) for item in reserved.items] == [(LimitType.TOTAL_TOKENS, 30)]

        for _ in range(2):
            await service.finalize_usage_reservation(
                reservation.reservation_id,
                model="private-model-without-prices",
                input_tokens=11,
                output_tokens=7,
                cached_input_tokens=3,
                cost_microdollars=999999,
                cost_override=UsageCostBreakdown(None, None, None, 999.0),
            )
        await service.record_usage(key_id, model="unknown", input_tokens=2, output_tokens=3)
        await repository.increment_limit_usage(
            key_id, model="unknown", input_tokens=1, output_tokens=1, cost_microdollars=999999
        )
        limits = await repository.get_limits_by_key(key_id)
        token_limit = next(limit for limit in limits if limit.limit_type == LimitType.TOTAL_TOKENS)
        assert token_limit.current_value == 25
        assert await _legacy_snapshot(session, key_id) == historical
        record = await session.get(ApiKeyUsageReservation, reservation.reservation_id)
        assert record is not None
        assert record.cost_microdollars is None
        assert (record.input_tokens, record.output_tokens, record.cached_input_tokens) == (11, 7, 3)

        token_limit.max_value = 25
        await session.commit()
        with pytest.raises(ApiKeyRateLimitExceededError, match="total_tokens"):
            await service.enforce_limits_for_request(key_id, request_model="unknown")


async def test_token_edits_and_resets_preserve_historical_monetary_rules(async_client):
    created = await _create_token_key(async_client)
    key_id = created["id"]
    historical = await _seed_legacy_limits(key_id)

    for payload in (
        {"limits": [{"limitType": "input_tokens", "limitWindow": "weekly", "maxValue": 777}]},
        {"resetUsage": True},
        {"limits": [], "resetUsage": True},
    ):
        response = await async_client.patch(f"/api/api-keys/{key_id}", json=payload)
        assert response.status_code == 200
        async with SessionLocal() as session:
            assert await _legacy_snapshot(session, key_id) == historical

    async with SessionLocal() as session:
        repository = ApiKeysRepository(session)
        for method in (repository.replace_limits, repository.upsert_limits):
            await method(
                key_id,
                [
                    ApiKeyLimit(
                        api_key_id=key_id,
                        limit_type=LimitType.OUTPUT_TOKENS,
                        limit_window=LimitWindow.DAILY,
                        max_value=100,
                        current_value=5,
                        reset_at=utcnow() + timedelta(days=1),
                    )
                ],
            )
            assert await _legacy_snapshot(session, key_id) == historical
            for limit_type in (LimitType.COST_USD, LimitType.CREDITS):
                with pytest.raises(ValueError, match="Only token limits"):
                    await method(
                        key_id,
                        [ApiKeyLimit(limit_type=limit_type, limit_window=LimitWindow.DAILY, max_value=100)],
                    )
            assert await _legacy_snapshot(session, key_id) == historical


async def test_lazy_and_scheduled_resets_do_not_change_legacy_money_limits(async_client):
    created = await _create_token_key(async_client)
    key_id = created["id"]
    historical = await _seed_legacy_limits(key_id)
    now = utcnow()

    async with SessionLocal() as session:
        repository = ApiKeysRepository(session)
        limits = await repository.get_limits_by_key(key_id)
        token_limit = next(limit for limit in limits if limit.limit_type == LimitType.TOTAL_TOKENS)
        token_limit.current_value = 900
        token_limit.reset_at = now - timedelta(days=2)
        await session.commit()
        await ApiKeysService(repository).validate_key(created["key"])
        await session.refresh(token_limit)
        assert token_limit.current_value == 0
        assert token_limit.reset_at > now
        assert await _legacy_snapshot(session, key_id) == historical

        token_limit.reset_at = now - timedelta(days=2)
        token_limit.current_value = 800
        await session.commit()
        assert await repository.reset_expired_limits(now=now) == 1
        for limit in limits:
            if limit.limit_type in TOKEN_LIMIT_TYPES:
                continue
            assert not await repository.reset_limit(
                limit.id, expected_reset_at=limit.reset_at, new_reset_at=now + timedelta(days=1)
            )
            assert not await repository.adjust_reserved_usage(limit.id, delta=-1, expected_reset_at=limit.reset_at)
            result = await repository.try_reserve_usage(limit.id, delta=1, expected_reset_at=limit.reset_at)
            assert result.success is False
        assert await _legacy_snapshot(session, key_id) == historical


@pytest.mark.parametrize("operation", ["finalize", "fail", "release", "stale_release"])
async def test_old_mixed_reservations_settle_tokens_without_rewriting_money_history(async_client, operation):
    created = await _create_token_key(async_client)
    key_id = created["id"]
    historical = await _seed_legacy_limits(key_id, expired=False)
    reservation_id = "legacy-mixed-reservation"

    async with SessionLocal() as session:
        repository = ApiKeysRepository(session)
        limits = await repository.get_limits_by_key(key_id)
        token_limit = next(limit for limit in limits if limit.limit_type == LimitType.TOTAL_TOKENS)
        token_limit.current_value = 30
        reservation = ApiKeyUsageReservation(
            id=reservation_id,
            api_key_id=key_id,
            model="unknown-legacy-model",
            status="reserved",
            cost_microdollars=987,
            created_at=utcnow() - timedelta(days=2),
            updated_at=utcnow() - timedelta(days=2),
        )
        session.add(reservation)
        await session.flush()
        for limit in limits:
            session.add(
                ApiKeyUsageReservationItem(
                    reservation_id=reservation_id,
                    limit_id=limit.id,
                    limit_type=limit.limit_type.value,
                    reserved_delta=30 if limit.limit_type in TOKEN_LIMIT_TYPES else 5,
                    expected_reset_at=limit.reset_at,
                    actual_delta=None,
                )
            )
        await session.commit()
        legacy_items_query = (
            select(ApiKeyUsageReservationItem.__table__)
            .where(
                ApiKeyUsageReservationItem.reservation_id == reservation_id,
                ApiKeyUsageReservationItem.limit_type.in_(["cost_usd", "credits"]),
            )
            .order_by(ApiKeyUsageReservationItem.id)
        )
        historical_items = (await session.execute(legacy_items_query)).all()
        service = ApiKeysService(repository)
        if operation == "finalize":
            await service.finalize_usage_reservation(
                reservation_id, model="unknown", input_tokens=5, output_tokens=2, cost_microdollars=123456
            )
        elif operation == "fail":
            await service.fail_usage_reservation(reservation_id, model="unknown", input_tokens=5, output_tokens=2)
        elif operation == "release":
            await service.release_usage_reservation(reservation_id)
        else:
            assert await repository.release_stale_usage_reservations(cutoff=utcnow() - timedelta(days=1)) == 1

        await session.refresh(token_limit)
        await session.refresh(reservation)
        assert token_limit.current_value == (7 if operation in {"finalize", "fail"} else 0)
        assert reservation.cost_microdollars == 987
        assert await _legacy_snapshot(session, key_id) == historical
        assert (await session.execute(legacy_items_query)).all() == historical_items
