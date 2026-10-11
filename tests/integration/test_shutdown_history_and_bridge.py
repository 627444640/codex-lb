"""Shutdown must release the history cache and requeued bridge waits."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections import deque
from types import SimpleNamespace

import anyio
import pytest

from app.core import shutdown as shutdown_state
from app.dependencies import get_proxy_service_for_app
from app.modules.proxy._service.support import _WebSocketRequestState
from app.modules.proxy.conversation_history import (
    ConversationHistoryCache,
    set_conversation_history_cache,
)

pytestmark = pytest.mark.integration


def _turn_body() -> dict[str, object]:
    return {
        "model": "gpt-5.1",
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "kept"}]}],
    }


@pytest.mark.asyncio
async def test_shutdown_closes_history_cache_and_fails_requeued_bridge_request(app_instance, tmp_path) -> None:
    cache = ConversationHistoryCache(
        tmp_path / "conversation_history.db",
        enabled=True,
        max_bytes=1024**3,
        conversation_max_bytes=32 * 1024 * 1024,
        idle_ttl_seconds=1800,
        min_free_disk_bytes=1,
        batch_limit=50,
        start_maintenance=True,
        disk_free=10 * 1024**3,
    )
    set_conversation_history_cache(cache)
    assert cache.record_completed_turn(
        request_body=_turn_body(),
        response_id="resp_shutdown_prev",
        output_items=[{"type": "message", "text": "ok"}],
    )
    assert cache._conn is not None
    maintenance = cache._maintenance
    assert maintenance is not None and maintenance.is_alive()

    request_state = _WebSocketRequestState(
        request_id="req_shutdown_requeue",
        model="gpt-5.1",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=time.monotonic(),
        event_queue=asyncio.Queue(),
        requeued_pending_upstream=True,
        skip_request_log=True,
    )
    session = SimpleNamespace(
        pending_requests=deque([request_state]),
        pending_lock=anyio.Lock(),
        queued_request_count=1,
        account=SimpleNamespace(id="acct_shutdown"),
        response_create_gate=None,
    )
    started = asyncio.Event()
    received: list[str | None] = []

    async def waiter() -> None:
        shutdown_state.increment_in_flight()
        started.set()
        try:
            assert request_state.event_queue is not None
            received.append(await request_state.event_queue.get())
        finally:
            shutdown_state.decrement_in_flight()

    task = asyncio.create_task(waiter())
    shutdown_started = time.monotonic()
    try:
        async with app_instance.router.lifespan_context(app_instance):
            service = get_proxy_service_for_app(app_instance)
            service._http_bridge_sessions["shutdown-requeue"] = session
            await started.wait()
            await asyncio.sleep(0)
            shutdown_started = time.monotonic()
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    elapsed = time.monotonic() - shutdown_started
    assert elapsed < 5.0, f"shutdown took {elapsed:.1f}s"
    assert task.done()
    assert received and received[0] is not None and "upstream_unavailable" in received[0]
    assert request_state not in session.pending_requests
    assert shutdown_state.get_in_flight() == 0
    assert cache._conn is None
    assert maintenance is not None and not maintenance.is_alive()
    live_cache_threads = [
        thread.name
        for thread in threading.enumerate()
        if thread.name == "conversation-history-cache" and thread.is_alive()
    ]
    assert live_cache_threads == []
    with sqlite3.connect(cache.path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM turns").fetchone()
    assert count is not None and count[0] == 1
