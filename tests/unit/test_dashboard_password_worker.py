from __future__ import annotations

import asyncio
import threading

import anyio
import pytest

from app.modules.dashboard_auth.service import _run_password_work

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _wait_for_count(calls: list[str], count: int) -> None:
    async with asyncio.timeout(2):
        while len(calls) < count:
            await asyncio.sleep(0.001)


async def test_cancelled_workers_keep_capacity_until_finished_and_waiters_do_not_submit():
    release = threading.Event()
    calls: list[str] = []

    def work(value: str) -> str:
        calls.append(value)
        assert release.wait(3)
        return value

    tasks = [asyncio.create_task(_run_password_work(work, value)) for value in ("first", "second")]
    try:
        await _wait_for_count(calls, 2)
        waiter = asyncio.create_task(_run_password_work(work, "cancelled-waiter"))
        tasks.append(waiter)
        await asyncio.sleep(0.01)
        waiter.cancel()
        for task in tasks[:2]:
            task.cancel()
        await asyncio.sleep(0.01)
        # A second native cancellation cannot release the worker's permit either.
        tasks[0].cancel()
        fourth = asyncio.create_task(_run_password_work(work, "fourth"))
        tasks.append(fourth)
        await asyncio.sleep(0.02)
        assert set(calls) == {"first", "second"}
        assert not tasks[0].done()
        assert not tasks[1].done()
    finally:
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(result, asyncio.CancelledError) for result in results[:3])
    assert results[3] == "fourth"
    assert "cancelled-waiter" not in calls


async def test_anyio_scope_cancellation_owns_worker_and_propagates_after_completion():
    release = threading.Event()
    calls: list[str] = []
    completed: list[str] = []

    def work(value: str) -> str:
        calls.append(value)
        assert release.wait(3)
        return value

    async def scoped_worker(*, task_status=anyio.TASK_STATUS_IGNORED):
        with anyio.CancelScope() as scope:
            task_status.started(scope)
            completed.append(await _run_password_work(work, "worker"))

    async with anyio.create_task_group() as group:
        scope = await group.start(scoped_worker)
        try:
            await _wait_for_count(calls, 1)
            scope.cancel()
            await asyncio.sleep(0.01)
            assert completed == []
        finally:
            release.set()
    assert completed == []

    # Both success and failure return the admission slot for subsequent work.
    def fail() -> str:
        raise ValueError("worker failed")

    with pytest.raises(ValueError, match="worker failed"):
        await _run_password_work(fail)
    assert await _run_password_work(str, "next") == "next"
