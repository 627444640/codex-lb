"""Request-scoped transparent-resend budget shared across proxy transports.

The budget is deliberately independent of the admission breaker's policy
state. Admission failover and history replay consume the same one-resend
allowance, including for long-lived websocket or HTTP-bridge tasks that serve
multiple requests in one task. Callers pass the request id for those tasks so
a later request still receives its own allowance.
"""

from __future__ import annotations

from contextvars import ContextVar

_transparent_retry_used: ContextVar[bool] = ContextVar("transparent_retry_used", default=False)
_transparent_retry_request_ids: ContextVar[frozenset[str]] = ContextVar(
    "transparent_retry_request_ids",
    default=frozenset(),
)


def transparent_retry_used(request_id: str | None = None) -> bool:
    """Return whether this request has already consumed its hidden resend."""

    if request_id is not None:
        return request_id in _transparent_retry_request_ids.get()
    return _transparent_retry_used.get()


def mark_transparent_retry(request_id: str | None = None) -> None:
    """Consume the single pre-output resend shared by failover and replay."""

    _transparent_retry_used.set(True)
    if not request_id:
        return
    used_ids = _transparent_retry_request_ids.get()
    if request_id in used_ids:
        return
    _transparent_retry_request_ids.set(frozenset((*used_ids, request_id)))


def reset_transparent_retry() -> None:
    """Clear the shared resend budget for a new request context or test."""

    _transparent_retry_used.set(False)
    _transparent_retry_request_ids.set(frozenset())
