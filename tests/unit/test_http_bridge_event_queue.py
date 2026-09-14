from __future__ import annotations

import asyncio
import time
from collections import deque
from contextlib import nullcontext
from typing import Any, cast

import anyio
import pytest

from app.modules.proxy.http_bridge_event_queue import (
    DownstreamBufferOverflow,
    EventBufferBudget,
    HTTPBridgeEventQueue,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_queue_consumption_and_discard_return_shared_byte_budget() -> None:
    budget = EventBufferBudget(1024)
    queue = HTTPBridgeEventQueue(budget, max_bytes=1024)
    await queue.put("中文😀")
    await queue.put("next")
    initial = budget.retained_bytes
    assert initial > len("中文😀next".encode())
    assert await queue.get() == "中文😀"
    assert 0 < budget.retained_bytes < initial
    queue.discard()
    queue.discard()
    assert budget.retained_bytes == 0
    await queue.put("ignored after detach")
    assert await queue.get() is None
    assert budget.retained_bytes == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("shared_limit", [False, True])
async def test_overflow_fails_only_producing_queue_and_never_waits(shared_limit: bool) -> None:
    budget = EventBufferBudget(360 if shared_limit else 4096)
    healthy = HTTPBridgeEventQueue(budget, max_bytes=4096)
    slow = HTTPBridgeEventQueue(budget, max_bytes=4096 if shared_limit else 300)
    await healthy.put("healthy")
    healthy_bytes = healthy.retained_bytes
    await slow.put("x" * 100)
    await asyncio.wait_for(slow.put("y" * 200), timeout=0.1)
    assert slow.overflowed
    assert slow.retained_bytes == 0
    assert budget.retained_bytes == healthy_bytes
    # Even a terminal producer must continue after overflow; no hidden success
    # may replace the explicit delivery error awaiting the consumer.
    await asyncio.wait_for(slow.put("response.completed"), timeout=0.1)
    await slow.put(None)
    with pytest.raises(DownstreamBufferOverflow):
        await asyncio.wait_for(slow.get(), timeout=0.1)
    assert await healthy.get() == "healthy"
    assert budget.retained_bytes == 0
    slow.discard()


@pytest.mark.asyncio
async def test_oversized_event_wakes_already_waiting_consumer() -> None:
    queue = HTTPBridgeEventQueue(EventBufferBudget(100), max_bytes=100)
    consumer = asyncio.create_task(queue.get())
    await asyncio.sleep(0)
    await queue.put("x" * 200)
    with pytest.raises(DownstreamBufferOverflow):
        await asyncio.wait_for(consumer, timeout=0.1)
    queue.discard()


@pytest.mark.asyncio
async def test_detached_overflow_keeps_upstream_request_deadline() -> None:
    from app.modules.proxy import service as proxy_service

    service = proxy_service.ProxyService(cast(Any, nullcontext()))
    state = proxy_service._WebSocketRequestState(
        request_id="overflow-deadline",
        model="gpt-5.1",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=time.monotonic() - 2,
        draining_until_terminal=True,
        downstream_buffer_overflowed=True,
    )
    timeout = await service._next_websocket_receive_timeout(
        deque([state]),
        pending_lock=anyio.Lock(),
        proxy_request_budget_seconds=1,
        stream_idle_timeout_seconds=300,
    )
    assert timeout is not None
    assert timeout.timeout_seconds == 0
    assert timeout.error_code == "upstream_request_timeout"
