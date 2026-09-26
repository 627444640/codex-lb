from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest
from sqlalchemy import select

import app.modules.proxy.service as proxy_module
from app.core.openai.models import CompactResponsePayload, OpenAIEvent
from app.core.types import JsonValue
from app.core.usage.validation import MAX_TOKEN_COUNT
from app.db.models import Account, ApiKeyLimit, ApiKeyUsageReservation, RequestLog
from app.db.session import SessionLocal
from app.dependencies import get_proxy_service_for_app
from app.modules.api_keys.repository import ApiKeysRepository
from app.modules.api_keys.service import ApiKeyCreateData, ApiKeyRequestUsageBudget, ApiKeysService, LimitRuleInput
from tests.integration.test_model_source_routing import _enable_api_key_auth
from tests.integration.test_proxy_files import _import_account

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _key_with_previous_usage(session):
    repository = ApiKeysRepository(session)
    service = ApiKeysService(repository)
    created = await service.create_key(
        ApiKeyCreateData(
            name="synthetic-usage-validation",
            allowed_models=None,
            limits=[LimitRuleInput(limit_type="total_tokens", limit_window="daily", max_value=1000)],
        )
    )
    [limit] = await repository.get_limits_by_key(created.id)
    limit.current_value = 100
    await session.commit()
    return repository, service, created, limit


async def _reserve(service, key_id):
    reservation = await service.enforce_limits_for_request(
        key_id,
        request_model="synthetic-model",
        request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=10, output_tokens=20),
    )
    assert reservation is not None
    return reservation


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens"])
@pytest.mark.parametrize("invalid", [-10, True, 1.5, "10", MAX_TOKEN_COUNT + 1])
async def test_direct_finalization_rejects_invalid_evidence_without_changing_prior_counter(db_setup, field, invalid):
    async with SessionLocal() as session:
        repository, service, created, limit = await _key_with_previous_usage(session)
        reservation = await _reserve(service, created.id)
        values: dict[str, Any] = {"input_tokens": 10, "output_tokens": 5, field: invalid}

        with pytest.raises(ValueError, match=f"^{field} must be a non-negative integer"):
            await service.finalize_usage_reservation(reservation.reservation_id, model="synthetic-model", **values)

        await session.refresh(limit)
        stored = await repository.get_usage_reservation(reservation.reservation_id)
        assert limit.current_value == 130
        assert stored is not None and stored.status == "reserved"
        assert stored.items[0].actual_delta is None

        await service.release_usage_reservation(reservation.reservation_id)
        await service.release_usage_reservation(reservation.reservation_id)
        await session.refresh(limit)
        assert limit.current_value == 100
        # A terminal reservation stays idempotent even if a late caller sends
        # malformed numbers again; it must not throw or reapply a delta.
        await service.finalize_usage_reservation(reservation.reservation_id, model="synthetic-model", **values)
        await session.refresh(limit)
        assert limit.current_value == 100


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
async def test_direct_finalization_requires_measured_core_counts(db_setup, field):
    async with SessionLocal() as session:
        _, service, created, limit = await _key_with_previous_usage(session)
        reservation = await _reserve(service, created.id)
        values: dict[str, Any] = {"input_tokens": 10, "output_tokens": 5, field: None}
        with pytest.raises(ValueError, match=field):
            await service.finalize_usage_reservation(reservation.reservation_id, model="synthetic-model", **values)
        await service.release_usage_reservation(reservation.reservation_id)
        await session.refresh(limit)
        assert limit.current_value == 100


@pytest.mark.parametrize(("input_tokens", "output_tokens", "expected"), [(10, 5, 115), (0, 0, 100)])
async def test_valid_refund_zero_and_terminal_idempotency_are_preserved(
    db_setup, input_tokens, output_tokens, expected
):
    async with SessionLocal() as session:
        repository, service, created, limit = await _key_with_previous_usage(session)
        reservation = await _reserve(service, created.id)
        for _ in range(2):
            await service.finalize_usage_reservation(
                reservation.reservation_id,
                model="synthetic-model",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        await service.release_usage_reservation(reservation.reservation_id)
        await service.finalize_usage_reservation(
            reservation.reservation_id,
            model="synthetic-model",
            input_tokens=-10,
            output_tokens=5,
        )
        await session.refresh(limit)
        stored = await repository.get_usage_reservation(reservation.reservation_id)
        assert limit.current_value == expected
        assert stored is not None and stored.status == "finalized"
        assert stored.items[0].actual_delta == input_tokens + output_tokens


async def test_legacy_record_usage_cannot_bypass_counter_validation(db_setup):
    async with SessionLocal() as session:
        _, service, created, limit = await _key_with_previous_usage(session)
        with pytest.raises(ValueError, match="input_tokens"):
            await service.record_usage(created.id, model="synthetic-model", input_tokens=-10, output_tokens=5)
        await session.refresh(limit)
        assert limit.current_value == 100


@pytest.mark.parametrize("surface", ["responses", "compact"])
@pytest.mark.parametrize("invalid", [-10, True, 1.5, "10"])
async def test_native_route_preserves_success_but_releases_invalid_usage(
    async_client, app_instance, monkeypatch, surface, invalid
):
    await _import_account(async_client, "synthetic-usage-account", "usage@example.invalid")
    await _enable_api_key_auth(async_client)
    async with SessionLocal() as session:
        _, _, created, _ = await _key_with_previous_usage(session)
    raw = {
        "id": "synthetic-completed",
        "model": "gpt-5.4",
        "status": "completed",
        "output": [],
        "usage": {"input_tokens": invalid, "output_tokens": 5},
    }

    async def fake_stream(*args, **kwargs):
        yield f"data: {json.dumps({'type': 'response.completed', 'response': raw})}\n\n"

    async def fake_compact(*args, **kwargs):
        return CompactResponsePayload.model_validate({**raw, "object": "response.compact"})

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)
    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)
    response = await async_client.post(
        f"/backend-api/codex/responses{'/compact' if surface == 'compact' else ''}",
        headers={"Authorization": f"Bearer {created.key}"},
        json={"model": "gpt-5.4", "instructions": "synthetic", "input": [], "stream": True}
        if surface == "responses"
        else {"model": "gpt-5.4", "instructions": "synthetic", "input": []},
    )
    assert response.status_code == 200
    if surface == "responses":
        assert "response.completed" in response.text
    await get_proxy_service_for_app(app_instance).drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        counter = (
            await session.execute(select(ApiKeyLimit.current_value).where(ApiKeyLimit.api_key_id == created.id))
        ).scalar_one()
        reservation = (
            (
                await session.execute(
                    select(ApiKeyUsageReservation).where(ApiKeyUsageReservation.api_key_id == created.id)
                )
            )
            .scalars()
            .one()
        )
        log = (await session.execute(select(RequestLog).where(RequestLog.api_key_id == created.id))).scalars().one()
        assert counter == 100
        assert reservation.status == "released"
        assert (log.input_tokens, log.output_tokens) == (None, 5)
        assert log.status == "success"


@pytest.mark.parametrize("transport", ["http", "websocket"])
async def test_bridge_and_websocket_terminal_releases_negative_usage(async_client, app_instance, transport):
    await _import_account(async_client, "synthetic-ws-usage", "ws-usage@example.invalid")
    async with SessionLocal() as session:
        _, service, created, _ = await _key_with_previous_usage(session)
        reservation = await _reserve(service, created.id)
        account = (await session.execute(select(Account))).scalars().one()
    raw: dict[str, JsonValue] = {
        "type": "response.completed",
        "response": {"id": "synthetic-ws-completed", "usage": {"input_tokens": -10, "output_tokens": 5}},
    }
    state = proxy_module._WebSocketRequestState(
        request_id="synthetic-ws-request",
        model="synthetic-model",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=reservation,
        started_at=time.monotonic(),
        transport=transport,
    )
    proxy = get_proxy_service_for_app(app_instance)
    await proxy._finalize_websocket_request_state(
        state,
        account=account,
        account_id_value=account.id,
        event=OpenAIEvent.model_validate(raw),
        event_type="response.completed",
        payload=raw,
        api_key=created,
        upstream_control=proxy_module._WebSocketUpstreamControl(),
        response_create_gate=asyncio.Semaphore(1),
    )
    await proxy.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        counter = (
            await session.execute(select(ApiKeyLimit.current_value).where(ApiKeyLimit.api_key_id == created.id))
        ).scalar_one()
        stored = await ApiKeysRepository(session).get_usage_reservation(reservation.reservation_id)
        assert counter == 100
        assert stored is not None and stored.status == "released"
