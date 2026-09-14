from __future__ import annotations

import asyncio
import threading

import pytest

from app.modules.dashboard_auth import service as auth_service

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _wait_for_thread(event: threading.Event) -> None:
    async with asyncio.timeout(2):
        while not event.is_set():
            await asyncio.sleep(0.001)


async def test_password_setup_keeps_health_live_responsive(async_client, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    hash_password = auth_service._hash_password

    def blocked_hash(password: str) -> str:
        entered.set()
        assert release.wait(3), "event loop did not release password worker"
        return hash_password(password)

    monkeypatch.setattr(auth_service, "_hash_password", blocked_hash)
    setup = asyncio.create_task(
        async_client.post("/api/dashboard-auth/password/setup", json={"password": "password123"})
    )
    try:
        await _wait_for_thread(entered)
        live = await asyncio.wait_for(async_client.get("/health/live"), timeout=0.5)
        assert live.status_code == 200
        assert not setup.done()
    finally:
        release.set()
        result = await setup
    assert result.status_code == 200
    login = await async_client.post("/api/dashboard-auth/password/login", json={"password": "password123"})
    assert login.status_code == 200


async def test_cancelled_password_setup_does_not_persist_credentials(async_client, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def blocked_hash(password: str) -> str:
        entered.set()
        assert release.wait(3)
        return "cancelled-hash-must-not-be-saved"

    monkeypatch.setattr(auth_service, "_hash_password", blocked_hash)
    setup = asyncio.create_task(
        async_client.post("/api/dashboard-auth/password/setup", json={"password": "password123"})
    )
    try:
        await _wait_for_thread(entered)
        setup.cancel()
        await asyncio.sleep(0.01)
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await setup
    state = await async_client.get("/api/dashboard-auth/session")
    assert state.status_code == 200
    assert state.json()["passwordRequired"] is False
