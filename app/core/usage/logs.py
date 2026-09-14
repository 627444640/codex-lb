from __future__ import annotations

from math import isclose
from typing import Literal, Protocol

from app.core.usage.pricing import (
    MODEL_SOURCE_PRICING_VERSION,
    PRICING_VERSION,
    UsageCostBreakdown,
    UsageTokens,
    calculate_cost_breakdown_from_usage,
    calculate_cost_from_usage,
    get_pricing_for_model,
)

# Request-log status classification shared by every error-metric surface
# (usage builders, time rollups, reports, fleet): `cancelled` is a normal
# client-side terminal (written when the downstream client disconnects before
# the final event lands — routing health already treats it as non-penalizing),
# so only statuses outside this tuple count as errors.
CANCELLED_STATUS = "cancelled"
NON_ERROR_STATUSES: tuple[str, ...] = ("success", CANCELLED_STATUS)
# The error code cancelled rows carry; excluded read-side from historical
# error-satellite rollup rows that were folded under the legacy
# `status != 'success'` filter.
CLIENT_DISCONNECT_ERROR_CODE = "client_disconnected"


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


CostStatus = Literal["estimated", "incomplete_usage", "unknown_model", "missing_usage", "historical"]


def cost_status_from_log(log: RequestLogLike) -> CostStatus:
    if log.pricing_version == MODEL_SOURCE_PRICING_VERSION:
        return "estimated" if log.cost_usd is not None else "missing_usage"
    if log.cost_usd is not None and log.pricing_version != PRICING_VERSION:
        return "historical"
    model = log.actual_model or log.model
    resolved = get_pricing_for_model(model) if model else None
    if resolved is None:
        return "estimated" if log.cost_usd is not None else "unknown_model"
    if log.input_tokens is None or log.output_tokens is None:
        return "missing_usage" if log.cost_usd is None else "incomplete_usage"
    _, price = resolved
    if log.cached_input_tokens is None or (price.cache_write_multiplier is not None and log.cache_write_tokens is None):
        return "incomplete_usage"
    if price.image_input_per_1m is not None and log.cost_usd is None:
        return "incomplete_usage"
    return "estimated"


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


def calculated_cost_from_log(log: RequestLogLike, *, precision: int | None = None) -> float | None:
    model = log.actual_model or log.model
    if not model:
        return None
    usage = usage_tokens_from_log(log)
    if not usage:
        return None
    resolved = get_pricing_for_model(model, None, None)
    if not resolved:
        return None
    _, price = resolved
    cost = calculate_cost_from_usage(usage, price, service_tier=log.service_tier)
    if cost is None:
        return None
    if precision is None:
        return cost
    return round(cost, precision)


def cost_from_log(log: RequestLogLike, *, precision: int | None = None) -> float | None:
    cost = log.cost_usd
    if cost is None:
        return None
    if precision is None:
        return float(cost)
    return round(float(cost), precision)


def _totals_match(left: float | None, right: float | None, *, precision: int | None) -> bool:
    if left is None or right is None:
        return False
    if precision is None:
        return isclose(left, right, rel_tol=1e-12, abs_tol=1e-15)
    return abs(left - right) < (10 ** (-precision)) / 2


def cost_breakdown_from_log(log: RequestLogLike, *, precision: int | None = None) -> UsageCostBreakdown:
    if log.pricing_version == MODEL_SOURCE_PRICING_VERSION:
        # Source configuration may use different rates or per-minute prices.
        # Public model rates cannot reconstruct its persisted components.
        return UsageCostBreakdown(None, None, None, cost_from_log(log, precision=precision))
    full_breakdown: UsageCostBreakdown | None = None
    input_usd: float | None = None
    cached_input_usd: float | None = None
    cache_write_usd: float | None = None
    output_usd: float | None = None
    raw_total_usd: float | None = None
    total_usd: float | None = None
    model = log.actual_model or log.model
    if model:
        resolved = get_pricing_for_model(model, None, None)
        if resolved is not None:
            _, price = resolved
            if log.pricing_version is not None and price.image_input_per_1m is not None and log.cost_usd is None:
                # A new image row has already been priced using its full
                # modality evidence. None is an explicit unknown, not an
                # invitation to recalculate after that evidence was discarded.
                return UsageCostBreakdown(None, None, None, None)
            input_tokens = log.input_tokens
            cached_tokens = cached_input_tokens_from_log(log)
            output_tokens = output_tokens_from_log(log)
            usage = usage_tokens_from_log(log)
            if usage is not None:
                raw_full_breakdown = calculate_cost_breakdown_from_usage(usage, price, service_tier=log.service_tier)
                if raw_full_breakdown is not None:
                    raw_total_usd = raw_full_breakdown.total_usd
                full_breakdown = calculate_cost_breakdown_from_usage(
                    usage,
                    price,
                    service_tier=log.service_tier,
                    precision=precision,
                )
                if full_breakdown is not None:
                    total_usd = full_breakdown.total_usd
            if input_tokens is not None and cached_tokens is not None:
                input_breakdown = calculate_cost_breakdown_from_usage(
                    UsageTokens(
                        input_tokens=float(input_tokens),
                        output_tokens=0.0,
                        cached_input_tokens=float(cached_tokens),
                        cache_write_tokens=float(cache_write_tokens_from_log(log) or 0),
                    ),
                    price,
                    service_tier=log.service_tier,
                    precision=precision,
                )
                if input_breakdown is not None:
                    input_usd = input_breakdown.input_usd
                    cached_input_usd = input_breakdown.cached_input_usd
                    cache_write_usd = input_breakdown.cache_write_usd
            if output_tokens is not None:
                output_breakdown = calculate_cost_breakdown_from_usage(
                    UsageTokens(
                        input_tokens=float(input_tokens or 0),
                        output_tokens=float(output_tokens),
                        cached_input_tokens=float(cached_tokens or 0),
                        cache_write_tokens=float(cache_write_tokens_from_log(log) or 0),
                    ),
                    price,
                    service_tier=log.service_tier,
                    precision=precision,
                )
                if output_breakdown is not None:
                    output_usd = output_breakdown.output_usd

    persisted_cost = cost_from_log(log, precision=precision)
    if persisted_cost is not None:
        persisted_raw_cost = cost_from_log(log)
        if not _totals_match(persisted_raw_cost, raw_total_usd, precision=precision):
            return UsageCostBreakdown(
                input_usd=None,
                cached_input_usd=None,
                output_usd=None,
                total_usd=persisted_cost,
            )
        return UsageCostBreakdown(
            input_usd=input_usd,
            cached_input_usd=cached_input_usd,
            cache_write_usd=cache_write_usd,
            output_usd=output_usd,
            total_usd=persisted_cost,
        )
    if full_breakdown is not None:
        return UsageCostBreakdown(
            input_usd=input_usd,
            cached_input_usd=cached_input_usd,
            cache_write_usd=cache_write_usd,
            output_usd=output_usd,
            total_usd=total_usd,
        )
    return UsageCostBreakdown(
        input_usd=input_usd,
        cached_input_usd=cached_input_usd,
        cache_write_usd=cache_write_usd,
        output_usd=output_usd,
        total_usd=None,
    )


def total_tokens_from_log(log: RequestLogLike) -> int | None:
    input_tokens = log.input_tokens
    output_tokens = output_tokens_from_log(log)
    if input_tokens is None and output_tokens is None:
        return None
    return (input_tokens or 0) + (output_tokens or 0)
