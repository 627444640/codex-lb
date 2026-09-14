"""Bound downstream event retention without blocking a shared upstream reader."""

from __future__ import annotations

import asyncio
import struct
import sys
from dataclasses import dataclass

# Two maximum-size default SSE frames per consumer, eight such buffers per
# process. These are local memory safeguards, not upstream protocol settings.
_REQUEST_MAX_BYTES = 32 * 1024 * 1024
_PROCESS_MAX_BYTES = 256 * 1024 * 1024
_REFERENCE_BYTES = struct.calcsize("P")
DOWNSTREAM_BUFFER_OVERFLOW = "downstream_buffer_overflow"


class DownstreamBufferOverflow(Exception):
    """The consumer lost delivery; upstream execution must still be settled."""


@dataclass(slots=True)
class EventBufferBudget:
    max_bytes: int
    retained_bytes: int = 0


_process_budget = EventBufferBudget(_PROCESS_MAX_BYTES)


class HTTPBridgeEventQueue(asyncio.Queue[str | None]):
    """Event-loop-local FIFO with fail-fast byte admission and shared accounting.

    Producers never raise or wait on capacity: an overflow wakes the consumer
    with an explicit failure, while upstream persistence and terminal settlement
    continue. A zero-byte sentinel is reserved for waking the failed consumer.
    """

    def __init__(self, budget: EventBufferBudget, *, max_bytes: int) -> None:
        super().__init__()
        self._budget = budget
        self._max_bytes = max_bytes
        self._retained_bytes = 0
        self._discarded = False
        self.overflowed = False

    @property
    def retained_bytes(self) -> int:
        return self._retained_bytes

    @staticmethod
    def _event_bytes(item: str | None) -> int:
        return 0 if item is None else sys.getsizeof(item) + _REFERENCE_BYTES

    def put_nowait(self, item: str | None) -> None:
        if self._discarded or self.overflowed:
            return
        size = self._event_bytes(item)
        if self._retained_bytes + size > self._max_bytes or self._budget.retained_bytes + size > self._budget.max_bytes:
            self.overflowed = True
            self._clear_buffer()
            super().put_nowait(None)
            return
        super().put_nowait(item)
        self._retained_bytes += size
        self._budget.retained_bytes += size

    def get_nowait(self) -> str | None:
        if self.overflowed:
            raise DownstreamBufferOverflow
        item = super().get_nowait()
        size = self._event_bytes(item)
        self._retained_bytes -= size
        self._budget.retained_bytes -= size
        return item

    def _clear_buffer(self) -> None:
        self._budget.retained_bytes -= self._retained_bytes
        self._retained_bytes = 0
        while not self.empty():
            super().get_nowait()
            self.task_done()

    def discard(self) -> None:
        if self._discarded:
            return
        self._discarded = True
        self._clear_buffer()
        super().put_nowait(None)

    def __del__(self) -> None:
        # Covers abandoned generators/prewarm setup before consumer ownership.
        self._budget.retained_bytes -= self._retained_bytes


def make_http_bridge_event_queue() -> HTTPBridgeEventQueue:
    return HTTPBridgeEventQueue(_process_budget, max_bytes=_REQUEST_MAX_BYTES)


def discard_http_bridge_event_queue(queue: asyncio.Queue[str | None] | None) -> None:
    if isinstance(queue, HTTPBridgeEventQueue):
        queue.discard()
