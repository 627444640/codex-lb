from __future__ import annotations

from typing import Literal, Protocol

from app.core.usage.pricing import UsageCostBreakdown, UsageTokens

CANCELLED_STATUS = "cancelled"
NON_ERROR_STATUSES: tuple[str, ...] = ("success", CANCELLED_STATUS)
CLIENT_DISCONNECT_ERROR_CODE = "client_disconnected"

# Old response vocabulary remains parseable; internal rows carry no amount.
CostStatus = Literal[
    "estimated",
    "incomplete_usage",
    "unknown_model",
    "unknown_pricing",
    "missing_usage",
    "historical",
    "not_applicable",
]
UsageStatus = Literal["complete", "partial", "missing"]


class RequestLogLike(Protocol):
    @property
    def model(self) -> str | None: ...

    @property
    def actual_model(self) -> str | None: ...

    @property
    def pricing_version(self) -> str | None: ...

    @property
    def cache_write_tokens(self) -> int | None: ...

    @property
    def service_tier(self) -> str | None: ...

    @property
    def input_tokens(self) -> int | None: ...

    @property
    def output_tokens(self) -> int | None: ...

    @property
    def cached_input_tokens(self) -> int | None: ...

    @property
    def reasoning_tokens(self) -> int | None: ...

    @property
    def cost_usd(self) -> float | None: ...


def cached_input_tokens_from_log(log: RequestLogLike) -> int | None:
    cached_tokens = log.cached_input_tokens
    if cached_tokens is None:
        return None
    cached_tokens = max(0, int(cached_tokens))
    input_tokens = log.input_tokens
    if input_tokens is not None:
        cached_tokens = min(cached_tokens, int(input_tokens))
    return cached_tokens


def cache_write_tokens_from_log(log: RequestLogLike) -> int | None:
    if log.cache_write_tokens is None:
        return None
    write_tokens = max(0, log.cache_write_tokens)
    if log.input_tokens is not None:
        write_tokens = min(write_tokens, max(0, log.input_tokens - (cached_input_tokens_from_log(log) or 0)))
    return write_tokens


def usage_tokens_from_log(log: RequestLogLike) -> UsageTokens | None:
    input_tokens = log.input_tokens
    if input_tokens is None:
        return None
    output_tokens = output_tokens_from_log(log)
    if output_tokens is None:
        return None
    cached_tokens = cached_input_tokens_from_log(log) or 0
    return UsageTokens(
        input_tokens=float(input_tokens),
        output_tokens=float(output_tokens),
        cached_input_tokens=float(cached_tokens),
        cache_write_tokens=float(cache_write_tokens_from_log(log) or 0),
    )


def output_tokens_from_log(log: RequestLogLike) -> int | None:
    output_tokens = log.output_tokens
    if output_tokens is not None:
        return int(output_tokens)
    reasoning_tokens = log.reasoning_tokens
    if reasoning_tokens is None:
        return None
    return int(reasoning_tokens)


def cost_from_log(log: RequestLogLike, *, precision: int | None = None) -> float | None:
    cost = log.cost_usd
    if cost is None:
        return None
    if precision is None:
        return float(cost)
    return round(float(cost), precision)


def total_tokens_from_log(log: RequestLogLike) -> int | None:
    input_tokens = log.input_tokens
    output_tokens = output_tokens_from_log(log)
    if input_tokens is None and output_tokens is None:
        return None
    return (input_tokens or 0) + (output_tokens or 0)


def usage_status_from_log(log: RequestLogLike) -> UsageStatus:
    """Describe total-token completeness using reported base counters.

    Cache and reasoning details are subsets, so their absence does not make
    a measured input/output total partial. Reasoning without output remains
    useful lower-bound evidence, but never substitutes for complete output.
    """
    if log.input_tokens is not None and log.output_tokens is not None:
        return "complete"
    if log.input_tokens is None and log.output_tokens is None and log.reasoning_tokens is None:
        return "missing"
    return "partial"


def cost_status_from_log(log: RequestLogLike) -> CostStatus:
    return "historical" if log.cost_usd is not None else "not_applicable"


def cost_breakdown_from_log(log: RequestLogLike, *, precision: int | None = None) -> UsageCostBreakdown:
    """Expose persisted history for compatibility without estimating prices."""
    return UsageCostBreakdown(None, None, None, cost_from_log(log, precision=precision))
