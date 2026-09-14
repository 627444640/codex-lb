from __future__ import annotations

import pytest

from app.core.openai.models import ResponseUsage, ResponseUsageDetails
from app.core.usage.pricing import (
    DEFAULT_MODEL_ALIASES,
    DEFAULT_PRICING_MODELS,
    CostItem,
    ModelPrice,
    UsageTokens,
    calculate_cost_breakdown_from_usage,
    calculate_cost_from_usage,
    calculate_costs,
    get_pricing_for_model,
    image_usage_tokens,
    resolve_model_alias,
)

pytestmark = pytest.mark.unit


def test_resolve_model_alias_longest_match():
    aliases = {
        "gpt-5*": "gpt-5",
        "gpt-5.1-codex*": "gpt-5.1-codex",
        "gpt-5.1-codex-max*": "gpt-5.1-codex-max",
    }
    assert resolve_model_alias("gpt-5.1-codex-max-2025", aliases) == "gpt-5.1-codex-max"


def test_get_pricing_for_model_alias():
    result = get_pricing_for_model("gpt-5.1-codex-mini-2025", DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result is not None
    model, price = result
    assert model == "gpt-5.1-codex-mini"
    assert price.output_per_1m == 2.0


def test_get_pricing_for_model_gpt_5_3_alias():
    result = get_pricing_for_model("gpt-5.3-codex-2026", DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result is not None
    model, _ = result
    assert model == "gpt-5.3-codex"


def test_get_pricing_for_model_gpt_5_3_chat_alias():
    result = get_pricing_for_model("gpt-5.3-chat-latest", DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result is not None
    model, _ = result
    assert model == "gpt-5.3-chat-latest"


def test_get_pricing_for_model_gpt_5_3_plain_alias():
    result = get_pricing_for_model("gpt-5.3-2026-01-01", DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result is not None
    model, _ = result
    assert model == "gpt-5.3"


def test_get_pricing_for_model_gpt_5_4_alias():
    result = get_pricing_for_model("gpt-5.4-2026", DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result is not None
    model, _ = result
    assert model == "gpt-5.4"


@pytest.mark.parametrize(
    ("requested_model", "canonical_model"),
    [
        ("gpt-5.6", "gpt-5.6-sol"),
        ("gpt-5.6-sol", "gpt-5.6-sol"),
        ("gpt-5.6-sol-2026-07-13", "gpt-5.6-sol"),
        ("gpt-5.6-terra", "gpt-5.6-terra"),
        ("gpt-5.6-terra-2026-07-13", "gpt-5.6-terra"),
        ("gpt-5.6-luna", "gpt-5.6-luna"),
        ("gpt-5.6-luna-2026-07-13", "gpt-5.6-luna"),
    ],
)
def test_get_pricing_for_model_gpt_5_6_aliases(requested_model: str, canonical_model: str) -> None:
    result = get_pricing_for_model(requested_model, DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)

    assert result == (canonical_model, DEFAULT_PRICING_MODELS[canonical_model])


def test_get_pricing_for_model_gpt_5_4_mini_alias():
    result = get_pricing_for_model("gpt-5.4-mini-2026-03-17", DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result is not None
    model, price = result
    assert model == "gpt-5.4-mini"
    assert price.input_per_1m == 0.75
    assert price.cached_input_per_1m == 0.075
    assert price.output_per_1m == 4.5


def test_get_pricing_for_model_gpt_5_4_nano_alias():
    result = get_pricing_for_model("gpt-5.4-nano-2026-03-17", DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result is not None
    model, price = result
    assert model == "gpt-5.4-nano"
    assert price.input_per_1m == 0.20
    assert price.cached_input_per_1m == 0.02
    assert price.output_per_1m == 1.25


def test_get_pricing_for_model_gpt_5_2_codex_alias():
    result = get_pricing_for_model("gpt-5.2-codex-2026-03-17", DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result is not None
    model, _ = result
    assert model == "gpt-5.2-codex"


def test_get_pricing_for_model_gpt_5_2_chat_latest_alias():
    result = get_pricing_for_model("gpt-5.2-chat-latest", DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result is not None
    model, _ = result
    assert model == "gpt-5.2-chat-latest"


def test_calculate_cost_from_usage_cached_tokens():
    usage = ResponseUsage(
        input_tokens=1000,
        output_tokens=500,
        input_tokens_details=ResponseUsageDetails(cached_tokens=200),
    )
    price = ModelPrice(input_per_1m=2.0, cached_input_per_1m=0.5, output_per_1m=4.0)
    cost = calculate_cost_from_usage(usage, price)
    expected = (800 / 1_000_000) * 2.0 + (200 / 1_000_000) * 0.5 + (500 / 1_000_000) * 4.0
    assert cost == pytest.approx(expected)


def test_calculate_cost_breakdown_from_usage_cached_tokens():
    usage = UsageTokens(
        input_tokens=1_000.0,
        output_tokens=500.0,
        cached_input_tokens=200.0,
    )
    price = ModelPrice(input_per_1m=2.0, cached_input_per_1m=0.5, output_per_1m=4.0)

    breakdown = calculate_cost_breakdown_from_usage(usage, price)

    assert breakdown is not None
    assert breakdown.input_usd == pytest.approx((800 / 1_000_000) * 2.0)
    assert breakdown.cached_input_usd == pytest.approx((200 / 1_000_000) * 0.5)
    assert breakdown.output_usd == pytest.approx((500 / 1_000_000) * 4.0)
    assert breakdown.total_usd == pytest.approx(
        ((800 / 1_000_000) * 2.0) + ((200 / 1_000_000) * 0.5) + ((500 / 1_000_000) * 4.0)
    )


def test_calculate_cost_breakdown_from_usage_clamps_cached_tokens():
    usage = UsageTokens(
        input_tokens=100.0,
        output_tokens=500.0,
        cached_input_tokens=200.0,
    )
    price = ModelPrice(input_per_1m=2.0, cached_input_per_1m=0.5, output_per_1m=4.0)

    breakdown = calculate_cost_breakdown_from_usage(usage, price)

    assert breakdown is not None
    assert breakdown.input_usd == pytest.approx(0.0)
    assert breakdown.cached_input_usd == pytest.approx((100 / 1_000_000) * 0.5)
    assert breakdown.output_usd == pytest.approx((500 / 1_000_000) * 4.0)
    assert breakdown.total_usd == pytest.approx(((100 / 1_000_000) * 0.5) + ((500 / 1_000_000) * 4.0))


def test_calculate_cost_breakdown_from_usage_priority_service_tier():
    usage = UsageTokens(
        input_tokens=1_000_000.0,
        output_tokens=1_000_000.0,
        cached_input_tokens=100_000.0,
    )
    price = ModelPrice(
        input_per_1m=2.5,
        cached_input_per_1m=0.25,
        output_per_1m=15.0,
        priority_input_per_1m=5.0,
        priority_cached_input_per_1m=0.5,
        priority_output_per_1m=30.0,
    )

    breakdown = calculate_cost_breakdown_from_usage(
        usage,
        price,
        service_tier="priority",
    )

    assert breakdown is not None
    assert breakdown.input_usd == pytest.approx(4.5)
    assert breakdown.cached_input_usd == pytest.approx(0.05)
    assert breakdown.output_usd == pytest.approx(30.0)
    assert breakdown.total_usd == pytest.approx(34.55)


def test_calculate_cost_breakdown_from_usage_precision_rounds_components_first():
    usage = UsageTokens(
        input_tokens=200_000.0,
        output_tokens=100_000.0,
        cached_input_tokens=100_000.0,
    )
    price = ModelPrice(input_per_1m=0.144, cached_input_per_1m=0.144, output_per_1m=0.144)

    breakdown = calculate_cost_breakdown_from_usage(usage, price, precision=2)

    assert breakdown is not None
    assert breakdown.input_usd == pytest.approx(0.01)
    assert breakdown.cached_input_usd == pytest.approx(0.01)
    assert breakdown.output_usd == pytest.approx(0.01)
    assert breakdown.total_usd == pytest.approx(0.03)


def test_calculate_cost_from_usage_priority_service_tier():
    usage = UsageTokens(input_tokens=1_000_000.0, output_tokens=1_000_000.0)
    price = DEFAULT_PRICING_MODELS["gpt-5.4"]

    cost = calculate_cost_from_usage(usage, price, service_tier="priority")

    assert cost == pytest.approx(35.0)


def test_calculate_cost_from_usage_flex_service_tier():
    usage = UsageTokens(input_tokens=1_000_000.0, output_tokens=1_000_000.0)
    price = DEFAULT_PRICING_MODELS["gpt-5.4-mini"]

    cost = calculate_cost_from_usage(usage, price, service_tier="flex")

    assert cost == pytest.approx(2.625)


@pytest.mark.parametrize(
    ("model", "service_tier", "expected_cost"),
    [
        ("gpt-5.6-sol", None, 20.44),
        ("gpt-5.6-sol", "flex", 10.22),
        ("gpt-5.6-sol", "priority", 40.88),
        ("gpt-5.6-sol", "fast", 40.88),
        ("gpt-5.6-terra", None, 12.22),
        ("gpt-5.6-terra", "flex", 6.11),
        ("gpt-5.6-terra", "priority", 24.44),
        ("gpt-5.6-terra", "fast", 24.44),
        ("gpt-5.6-luna", None, 1.222),
        ("gpt-5.6-luna", "flex", 0.611),
        ("gpt-5.6-luna", "priority", 2.444),
        ("gpt-5.6-luna", "fast", 2.444),
    ],
)
def test_calculate_cost_from_usage_gpt_5_6_service_tiers(
    model: str,
    service_tier: str | None,
    expected_cost: float,
) -> None:
    usage = UsageTokens(
        input_tokens=200_000.0,
        output_tokens=1_000_000.0,
        cached_input_tokens=100_000.0,
    )

    cost = calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS[model], service_tier=service_tier)

    assert cost == pytest.approx(expected_cost)


@pytest.mark.parametrize(
    ("model", "service_tier", "expected_cost"),
    [
        ("gpt-5.6-sol", None, 5.04),
        ("gpt-5.6-sol", "flex", 2.52),
        ("gpt-5.6-sol", "priority", 10.08),
        ("gpt-5.6-terra", None, 2.82),
        ("gpt-5.6-terra", "flex", 1.41),
        ("gpt-5.6-terra", "priority", 5.64),
        ("gpt-5.6-luna", None, 0.282),
        ("gpt-5.6-luna", "flex", 0.141),
        ("gpt-5.6-luna", "priority", 0.564),
    ],
)
def test_calculate_cost_from_usage_gpt_5_6_long_context(
    model: str,
    service_tier: str | None,
    expected_cost: float,
) -> None:
    usage = UsageTokens(
        input_tokens=300_000.0,
        output_tokens=100_000.0,
        cached_input_tokens=50_000.0,
    )

    cost = calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS[model], service_tier=service_tier)

    assert cost == pytest.approx(expected_cost)


@pytest.mark.parametrize(
    ("model", "standard_input_rate", "long_context_input_rate"),
    [
        ("gpt-5.6-sol", 4.0, 8.0),
        ("gpt-5.6-terra", 2.0, 4.0),
        ("gpt-5.6-luna", 0.2, 0.4),
    ],
)
def test_calculate_cost_from_usage_gpt_5_6_uses_272k_long_context_boundary(
    model: str,
    standard_input_rate: float,
    long_context_input_rate: float,
) -> None:
    price = DEFAULT_PRICING_MODELS[model]

    at_boundary = calculate_cost_from_usage(UsageTokens(input_tokens=272_000.0, output_tokens=0.0), price)
    above_boundary = calculate_cost_from_usage(UsageTokens(input_tokens=272_001.0, output_tokens=0.0), price)

    assert at_boundary == pytest.approx(272_000 / 1_000_000 * standard_input_rate)
    assert above_boundary == pytest.approx(272_001 / 1_000_000 * long_context_input_rate)


def test_calculate_cost_from_usage_service_tier_trims_whitespace():
    usage = UsageTokens(input_tokens=1_000_000.0, output_tokens=1_000_000.0)
    priority_price = DEFAULT_PRICING_MODELS["gpt-5.4"]
    flex_price = DEFAULT_PRICING_MODELS["gpt-5.4-mini"]

    priority_cost = calculate_cost_from_usage(usage, priority_price, service_tier=" priority ")
    flex_cost = calculate_cost_from_usage(usage, flex_price, service_tier=" flex ")

    assert priority_cost == pytest.approx(35.0)
    assert flex_cost == pytest.approx(2.625)


def test_calculate_cost_from_usage_legacy_gpt_5_service_tiers() -> None:
    usage = UsageTokens(input_tokens=1_000_000.0, output_tokens=1_000_000.0)

    gpt_5_priority = calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-5"], service_tier="priority")
    gpt_5_1_flex = calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-5.1"], service_tier="flex")
    gpt_5_2_priority = calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-5.2"], service_tier="priority")
    gpt_5_2_flex = calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-5.2"], service_tier="flex")

    assert gpt_5_priority == pytest.approx(22.5)
    assert gpt_5_1_flex == pytest.approx(5.625)
    assert gpt_5_2_priority == pytest.approx(31.5)
    assert gpt_5_2_flex == pytest.approx(7.875)


def test_calculate_cost_from_usage_unsupported_tiers_fall_back_to_standard():
    usage = UsageTokens(input_tokens=1_000_000.0, output_tokens=1_000_000.0)
    codex_mini = DEFAULT_PRICING_MODELS["gpt-5.1-codex-mini"]
    gpt_5_3_chat = DEFAULT_PRICING_MODELS["gpt-5.3-chat-latest"]
    gpt_5_2_chat = DEFAULT_PRICING_MODELS["gpt-5.2-chat-latest"]

    codex_mini_priority = calculate_cost_from_usage(usage, codex_mini, service_tier="priority")
    codex_mini_flex = calculate_cost_from_usage(usage, codex_mini, service_tier="flex")
    gpt_5_3_chat_priority = calculate_cost_from_usage(usage, gpt_5_3_chat, service_tier="priority")
    gpt_5_2_chat_priority = calculate_cost_from_usage(usage, gpt_5_2_chat, service_tier="priority")
    gpt_5_2_chat_flex = calculate_cost_from_usage(usage, gpt_5_2_chat, service_tier="flex")

    assert codex_mini_priority == pytest.approx(2.25)
    assert codex_mini_flex == pytest.approx(2.25)
    assert gpt_5_3_chat_priority == pytest.approx(15.75)
    assert gpt_5_2_chat_priority == pytest.approx(15.75)
    assert gpt_5_2_chat_flex == pytest.approx(15.75)


def test_calculate_cost_from_usage_gpt_5_2_codex_priority():
    usage = UsageTokens(input_tokens=1_000_000.0, output_tokens=1_000_000.0)
    price = DEFAULT_PRICING_MODELS["gpt-5.2-codex"]

    cost = calculate_cost_from_usage(usage, price, service_tier="priority")

    assert cost == pytest.approx(31.5)


def test_calculate_cost_from_usage_gpt_5_4_pro_flex():
    usage = UsageTokens(input_tokens=200_000.0, output_tokens=1_000_000.0)
    price = DEFAULT_PRICING_MODELS["gpt-5.4-pro"]

    cost = calculate_cost_from_usage(usage, price, service_tier="flex")

    assert cost == pytest.approx(93.0)


def test_calculate_cost_from_usage_gpt_5_4_long_context():
    usage = UsageTokens(
        input_tokens=300_000.0,
        output_tokens=100_000.0,
        cached_input_tokens=50_000.0,
    )
    price = DEFAULT_PRICING_MODELS["gpt-5.4"]

    cost = calculate_cost_from_usage(usage, price)

    expected = (250_000 / 1_000_000) * 5.0 + (50_000 / 1_000_000) * 0.5 + (100_000 / 1_000_000) * 22.5
    assert cost == pytest.approx(expected)


def test_calculate_cost_from_usage_gpt_5_4_long_context_flex():
    usage = UsageTokens(
        input_tokens=300_000.0,
        output_tokens=100_000.0,
        cached_input_tokens=50_000.0,
    )
    price = DEFAULT_PRICING_MODELS["gpt-5.4"]

    cost = calculate_cost_from_usage(usage, price, service_tier="flex")

    expected = (250_000 / 1_000_000) * 2.5 + (50_000 / 1_000_000) * 0.25 + (100_000 / 1_000_000) * 11.25
    assert cost == pytest.approx(expected)


def test_calculate_cost_from_usage_gpt_5_4_mini():
    usage = UsageTokens(
        input_tokens=1_000_000.0,
        output_tokens=1_000_000.0,
        cached_input_tokens=100_000.0,
    )
    price = DEFAULT_PRICING_MODELS["gpt-5.4-mini"]

    cost = calculate_cost_from_usage(usage, price)

    expected = (900_000 / 1_000_000) * 0.75 + (100_000 / 1_000_000) * 0.075 + (1_000_000 / 1_000_000) * 4.5
    assert cost == pytest.approx(expected)


def test_calculate_cost_from_usage_gpt_5_4_nano():
    usage = UsageTokens(
        input_tokens=1_000_000.0,
        output_tokens=1_000_000.0,
        cached_input_tokens=100_000.0,
    )
    price = DEFAULT_PRICING_MODELS["gpt-5.4-nano"]

    cost = calculate_cost_from_usage(usage, price)

    expected = (900_000 / 1_000_000) * 0.20 + (100_000 / 1_000_000) * 0.02 + (1_000_000 / 1_000_000) * 1.25
    assert cost == pytest.approx(expected)


def test_calculate_costs_aggregates_by_model():
    items = [
        CostItem(model="gpt-5.1", usage=UsageTokens(input_tokens=1000.0, output_tokens=1000.0)),
        CostItem(model="gpt-5.1-variant", usage=UsageTokens(input_tokens=2000.0, output_tokens=1000.0)),
    ]
    result = calculate_costs(items, DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)
    assert result.currency == "USD"
    by_model = {entry.model: entry.usd for entry in result.by_model}
    assert "gpt-5.1" in by_model
    assert by_model["gpt-5.1"] > 0


def test_calculate_costs_uses_service_tier():
    items = [
        CostItem(
            model="gpt-5.4",
            service_tier="priority",
            usage=UsageTokens(input_tokens=1_000_000.0, output_tokens=1_000_000.0),
        ),
    ]

    result = calculate_costs(items, DEFAULT_PRICING_MODELS, DEFAULT_MODEL_ALIASES)

    assert result.total_usd_7d == pytest.approx(35.0)


@pytest.mark.parametrize("model", ["gpt-6-astra", "GPT-6-ASTRA", "gpt-6-astra-2026-09-14"])
def test_astra_pricing_and_snapshot_aliases(model: str) -> None:
    resolved = get_pricing_for_model(model)
    assert resolved is not None
    assert resolved[0] == "gpt-6-astra"
    assert calculate_cost_from_usage(UsageTokens(100_000, 1_000, 50_000), resolved[1]) == pytest.approx(0.6)


@pytest.mark.parametrize("model", ["codex-auto-review", "gpt-6-astra-unknown-variant", "gpt-6-unknown"])
def test_unpublished_model_prices_remain_unknown(model: str) -> None:
    assert get_pricing_for_model(model) is None


@pytest.mark.parametrize(
    ("model", "tier", "expected"),
    [
        ("gpt-5.5", "default", 3.045),
        ("gpt-5.5", "flex", 1.5225),
        ("gpt-5.5-pro", "default", 18.27),
        ("gpt-5.4-mini", "priority", 0.459),
        ("gpt-5.4-mini", "fast", 0.459),
        ("gpt-6-astra", "default", 6.075),
        ("gpt-6-astra", "flex", 3.0375),
        ("gpt-6-astra", "priority", 12.15),
        ("gpt-6-astra", "fast", 12.15),
    ],
)
def test_current_model_tier_and_long_context_rates(model: str, tier: str, expected: float) -> None:
    cost = calculate_cost_from_usage(UsageTokens(300_000, 1_000), DEFAULT_PRICING_MODELS[model], service_tier=tier)
    assert cost == pytest.approx(expected)


@pytest.mark.parametrize(("tier", "expected"), [("default", 0.0342), ("priority", 0.0684), ("flex", 0.0171)])
def test_cache_writes_are_disjoint_input_partition_with_tier_pricing(tier: str, expected: float) -> None:
    usage = ResponseUsage(
        input_tokens=100_000,
        output_tokens=10_000,
        input_tokens_details=ResponseUsageDetails(cached_tokens=10_000, cache_write_tokens=80_000),
        output_tokens_details=ResponseUsageDetails(reasoning_tokens=8_000),
    )
    result = calculate_cost_breakdown_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-5.6-luna"], service_tier=tier)
    assert result is not None
    # Standard: 10K ordinary * .2 + 10K cached * .02 + 80K written * .25
    # + 10K output * 1.2. Reasoning is already included in output.
    assert result.total_usd == pytest.approx(expected)
    assert result.input_usd is not None
    assert result.cached_input_usd is not None
    assert result.cache_write_usd is not None
    assert result.output_usd is not None
    assert result.total_usd == pytest.approx(
        result.input_usd + result.cached_input_usd + result.cache_write_usd + result.output_usd
    )


def test_cache_write_premium_uses_long_context_rate() -> None:
    usage = UsageTokens(300_000, 1_000, 100_000, 100_000)
    result = calculate_cost_breakdown_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-6-astra"], service_tier="priority")
    assert result is not None
    assert result.input_usd == pytest.approx(4.0)
    assert result.cached_input_usd == pytest.approx(0.4)
    assert result.cache_write_usd == pytest.approx(5.0)
    assert result.output_usd == pytest.approx(0.15)
    assert result.total_usd == pytest.approx(9.55)


@pytest.mark.parametrize(
    ("cached", "writes", "expected"), [(80, 80, 0.0000066), (200, 200, 0.000002), (-20, -20, 0.00002)]
)
def test_cache_partitions_never_exceed_input(cached: int, writes: int, expected: float) -> None:
    result = calculate_cost_from_usage(UsageTokens(100, 0, cached, writes), DEFAULT_PRICING_MODELS["gpt-5.6-luna"])
    assert result == pytest.approx(expected)


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_nonfinite_token_totals_do_not_produce_nonfinite_cost(value: float) -> None:
    assert calculate_cost_from_usage(UsageTokens(value, 1), DEFAULT_PRICING_MODELS["gpt-6-astra"]) is None


@pytest.mark.parametrize(
    ("model", "expected"),
    [("gpt-image-2", 0.02145), ("gpt-image-1.5", 0.02141), ("gpt-image-1", 0.02625), ("gpt-image-1-mini", 0.00644)],
)
def test_image_model_prices_preserve_text_image_and_cache_partitions(model: str, expected: float) -> None:
    usage = image_usage_tokens(
        input_tokens=3_000,
        output_tokens=200,
        input_tokens_details={
            "text_tokens": 1_000,
            "image_tokens": 2_000,
            "cached_tokens": 1_000,
            "cached_tokens_details": {"text_tokens": 200, "image_tokens": 800},
        },
        output_tokens_details={"text_tokens": 20} if model == "gpt-image-1.5" else None,
    )
    assert calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS[model]) == pytest.approx(expected)


@pytest.mark.parametrize("model", ["gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"])
def test_image_cost_is_unknown_without_input_modality_counts(model: str) -> None:
    assert calculate_cost_from_usage(UsageTokens(1_000, 100), DEFAULT_PRICING_MODELS[model]) is None


def test_mixed_image_input_with_missing_cached_partition_is_unknown() -> None:
    usage = image_usage_tokens(
        input_tokens=1_000,
        output_tokens=100,
        input_tokens_details={"image_tokens": 500, "cached_tokens": 100},
    )
    assert calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-image-2"]) is None


def test_text_only_image_prompt_deduces_cached_modality() -> None:
    usage = image_usage_tokens(
        input_tokens=1_000,
        output_tokens=100,
        input_tokens_details={"text_tokens": 1_000, "cached_tokens": 200},
    )
    assert calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-image-2"]) == pytest.approx(0.00725)


def test_image_model_with_text_output_requires_output_partition() -> None:
    usage = image_usage_tokens(input_tokens=0, output_tokens=100)
    assert calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-image-1.5"]) is None


def test_inconsistent_image_input_partitions_are_unknown() -> None:
    assert (
        image_usage_tokens(
            input_tokens=100,
            output_tokens=10,
            input_tokens_details={"image_tokens": 90, "text_tokens": 90},
        )
        is None
    )


def test_inconsistent_image_cache_partitions_are_unknown() -> None:
    assert (
        image_usage_tokens(
            input_tokens=100,
            output_tokens=10,
            input_tokens_details={
                "image_tokens": 50,
                "text_tokens": 50,
                "cached_tokens": 30,
                "cached_tokens_details": {"image_tokens": 25, "text_tokens": 25},
            },
        )
        is None
    )


def test_cached_image_partition_cannot_exceed_image_input() -> None:
    usage = UsageTokens(100, 10, 80, image_input_tokens=20, cached_image_input_tokens=40)
    assert calculate_cost_from_usage(usage, DEFAULT_PRICING_MODELS["gpt-image-2"]) is None
