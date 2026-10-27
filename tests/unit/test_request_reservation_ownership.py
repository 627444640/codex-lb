from __future__ import annotations

import asyncio
from contextlib import nullcontext
from typing import Any, cast

import pytest

from app.modules.api_keys.service import ApiKeyUsageReservationData
from app.modules.proxy import service as proxy_service

pytestmark = pytest.mark.unit


def _request(name: str) -> proxy_service._WebSocketRequestState:
    return proxy_service._WebSocketRequestState(
        request_id=name,
        model="gpt-5.5",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=ApiKeyUsageReservationData(reservation_id=name, key_id="key", model="gpt-5.5"),
        started_at=1.0,
    )


async def test_concurrent_request_cleanup_submits_one_live_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    state = _request("concurrent")
    started, finish = asyncio.Event(), asyncio.Event()
    writes: list[str] = []

    async def release(reservation: ApiKeyUsageReservationData | None) -> None:
        if reservation is None:
            return
        writes.append(reservation.reservation_id)
        started.set()
        await finish.wait()

    monkeypatch.setattr(service, "_release_websocket_reservation", release)
    first = asyncio.create_task(service._release_websocket_request_state_reservation(state))
    await started.wait()
    second = asyncio.create_task(service._release_websocket_request_state_reservation(state))
    try:
        await asyncio.sleep(0)
        assert writes == ["concurrent"]
    finally:
        finish.set()
        await asyncio.gather(first, second)
    assert writes == ["concurrent"]
    assert state.api_key_reservation is None


async def test_failed_writer_retains_reservation_for_waiting_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    state = _request("retry")
    started, fail = asyncio.Event(), asyncio.Event()
    attempts = 0

    async def release(reservation: ApiKeyUsageReservationData | None) -> None:
        nonlocal attempts
        if reservation is None:
            return
        attempts += 1
        if attempts == 1:
            started.set()
            await fail.wait()
            raise RuntimeError("unconfirmed write")

    monkeypatch.setattr(service, "_release_websocket_reservation", release)
    first = asyncio.create_task(service._release_websocket_request_state_reservation(state))
    await started.wait()
    second = asyncio.create_task(service._release_websocket_request_state_reservation(state))
    fail.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert isinstance(results[0], RuntimeError)
    assert results[1] is None
    assert attempts == 2
    assert state.api_key_reservation is None


async def test_cancelled_waiter_does_not_cancel_active_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    state = _request("cancel-waiter")
    started, finish = asyncio.Event(), asyncio.Event()
    writes = 0

    async def release(reservation: ApiKeyUsageReservationData | None) -> None:
        nonlocal writes
        if reservation is None:
            return
        writes += 1
        started.set()
        await finish.wait()

    monkeypatch.setattr(service, "_release_websocket_reservation", release)
    writer = asyncio.create_task(service._release_websocket_request_state_reservation(state))
    await started.wait()
    waiter = asyncio.create_task(service._release_websocket_request_state_reservation(state))
    try:
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert not writer.done()
        assert state.api_key_reservation is not None
    finally:
        finish.set()
        await writer
    assert writes == 1
    assert state.api_key_reservation is None


async def test_cancelled_writer_leaves_reservation_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    state = _request("cancel-writer")
    started, finish = asyncio.Event(), asyncio.Event()
    attempts = 0

    async def release(reservation: ApiKeyUsageReservationData | None) -> None:
        nonlocal attempts
        if reservation is None:
            return
        attempts += 1
        started.set()
        await finish.wait()

    monkeypatch.setattr(service, "_release_websocket_reservation", release)
    writer = asyncio.create_task(service._release_websocket_request_state_reservation(state))
    await started.wait()
    writer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await writer
    assert state.api_key_reservation is not None

    finish.set()
    await service._release_websocket_request_state_reservation(state)
    assert attempts == 2
    assert state.api_key_reservation is None


async def test_settlement_does_not_serialize_unrelated_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    first, second = _request("slow"), _request("independent")
    started, finish = asyncio.Event(), asyncio.Event()

    async def release(reservation: ApiKeyUsageReservationData | None) -> None:
        if reservation is not None and reservation.reservation_id == "slow":
            started.set()
            await finish.wait()

    monkeypatch.setattr(service, "_release_websocket_reservation", release)
    writer = asyncio.create_task(service._release_websocket_request_state_reservation(first))
    await started.wait()
    try:
        await asyncio.wait_for(service._release_websocket_request_state_reservation(second), timeout=3)
        assert second.api_key_reservation is None
        assert not writer.done()
    finally:
        finish.set()
        await writer
