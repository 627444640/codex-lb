from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from app.core.usage.logs import (
    RequestLogLike,
    cost_breakdown_from_log,
    cost_from_log,
    cost_status_from_log,
    total_tokens_from_log,
    usage_tokens_from_log,
)
from app.core.usage.pricing import (
    ModelPrice,
    UsageCostBreakdown,
    UsageTokens,
    calculate_cost_from_usage,
    get_pricing_for_model,
    image_usage_tokens,
)
from app.db.models import RequestLog

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("model", ["gpt-5.4", "gpt-6-astra", "private-model", ""])
def test_historical_migration_price_lookup_cannot_supply_prices(model: str) -> None:
    assert get_pricing_for_model(model) is None


def test_historical_migration_calculator_cannot_bill_even_with_explicit_rates() -> None:
    usage = UsageTokens(input_tokens=1000000, output_tokens=1000000, cached_input_tokens=500000)
    supplied_price = ModelPrice(input_per_1m=100.0, output_per_1m=200.0, cached_input_per_1m=50.0)
    assert calculate_cost_from_usage(usage, supplied_price) is None


def test_image_usage_keeps_measured_text_image_and_cached_partitions() -> None:
    usage = image_usage_tokens(
        input_tokens=3000,
        output_tokens=200,
        input_tokens_details={
            "text_tokens": 1000,
            "image_tokens": 2000,
            "cached_tokens": 1000,
            "cached_tokens_details": {"text_tokens": 200, "image_tokens": 800},
        },
        output_tokens_details={"text_tokens": 20, "image_tokens": 180},
    )
    assert usage == UsageTokens(
        input_tokens=3000,
        output_tokens=200,
        cached_input_tokens=1000,
        image_input_tokens=2000,
        cached_image_input_tokens=800,
        text_output_tokens=20,
    )


def test_image_usage_deduces_only_partitions_with_measured_totals() -> None:
    usage = image_usage_tokens(
        input_tokens=1000,
        output_tokens=100,
        input_tokens_details={
            "text_tokens": 600,
            "cached_tokens": 200,
            "cached_tokens_details": {"text_tokens": 150},
        },
        output_tokens_details={"image_tokens": 80},
    )
    assert usage is not None
    assert usage.image_input_tokens == 400
    assert usage.cached_image_input_tokens == 50
    assert usage.text_output_tokens == 20


def test_image_usage_keeps_missing_modality_counts_unknown() -> None:
    usage = image_usage_tokens(input_tokens=1000, output_tokens=100)
    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens) == (1000, 100)
    assert usage.image_input_tokens is None
    assert usage.cached_image_input_tokens is None
    assert usage.text_output_tokens is None


@pytest.mark.parametrize("input_tokens,output_tokens", [(None, 10), (10, None), (-1, 10), (10, -1)])
def test_image_usage_rejects_missing_or_negative_totals(input_tokens, output_tokens) -> None:
    assert image_usage_tokens(input_tokens=input_tokens, output_tokens=output_tokens) is None


@pytest.mark.parametrize(
    "input_details,output_details",
    [
        ({"image_tokens": 90, "text_tokens": 90}, None),
        (
            {
                "image_tokens": 50,
                "text_tokens": 50,
                "cached_tokens": 30,
                "cached_tokens_details": {"image_tokens": 25, "text_tokens": 25},
            },
            None,
        ),
        (None, {"image_tokens": 9, "text_tokens": 9}),
    ],
)
def test_image_usage_rejects_contradictory_measured_partitions(input_details, output_details) -> None:
    assert (
        image_usage_tokens(
            input_tokens=100,
            output_tokens=10,
            input_tokens_details=input_details,
            output_tokens_details=output_details,
        )
        is None
    )


@pytest.mark.parametrize("stored_amount", [None, 0.0, 0.00000002, 0.123456789, 123.45])
def test_cost_compatibility_reads_only_the_stored_amount(stored_amount: float | None) -> None:
    # No model, service tier or token attributes are available: an attempt to
    # reprice or infer component amounts would fail instead of returning data.
    log = cast(RequestLogLike, SimpleNamespace(cost_usd=stored_amount))
    assert cost_from_log(log) == stored_amount
    assert cost_status_from_log(log) == ("historical" if stored_amount is not None else "not_applicable")
    assert cost_breakdown_from_log(log) == UsageCostBreakdown(None, None, None, stored_amount)
    assert log.cost_usd == stored_amount


def test_cost_precision_changes_only_the_response_not_the_historical_amount() -> None:
    log = cast(RequestLogLike, SimpleNamespace(cost_usd=0.123456789))
    assert cost_breakdown_from_log(log, precision=6) == UsageCostBreakdown(None, None, None, 0.123457)
    assert cost_from_log(log) == 0.123456789


@pytest.mark.parametrize("pricing_version", [None, "openai-api-2026-09-17-v1", "model-source-config-v1"])
def test_missing_amount_is_never_estimated_from_model_or_tokens(pricing_version: str | None) -> None:
    log = RequestLog(
        model="gpt-5.4",
        actual_model="gpt-6-astra",
        service_tier="priority",
        pricing_version=pricing_version,
        input_tokens=1000000,
        output_tokens=1000000,
        cached_input_tokens=500000,
        cache_write_tokens=100000,
        cost_usd=None,
    )
    assert cost_breakdown_from_log(log) == UsageCostBreakdown(None, None, None, None)
    assert cost_status_from_log(log) == "not_applicable"
    assert log.cost_usd is None
    assert log.pricing_version == pricing_version
    assert total_tokens_from_log(log) == 2000000


def test_log_token_totals_keep_cached_and_write_partitions_disjoint() -> None:
    log = RequestLog(
        input_tokens=100,
        output_tokens=20,
        cached_input_tokens=80,
        cache_write_tokens=50,
        reasoning_tokens=10,
    )
    assert usage_tokens_from_log(log) == UsageTokens(100, 20, 80, 20)
    assert total_tokens_from_log(log) == 120
    assert (log.cached_input_tokens, log.cache_write_tokens) == (80, 50)


def test_log_output_falls_back_to_reasoning_only_when_output_is_missing() -> None:
    log = RequestLog(input_tokens=100, output_tokens=None, reasoning_tokens=20)
    assert usage_tokens_from_log(log) == UsageTokens(100, 20)
    assert total_tokens_from_log(log) == 120
    log.output_tokens = 0
    assert usage_tokens_from_log(log) == UsageTokens(100, 0)
    assert total_tokens_from_log(log) == 100
