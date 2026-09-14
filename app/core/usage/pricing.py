from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fnmatch import fnmatchcase
from math import isfinite
from typing import Iterable, Mapping

from app.core.openai.models import ResponseUsage
from app.core.types import JsonValue
from app.core.usage.types import UsageCostByModel, UsageCostSummary

# Retail API token estimates, not ChatGPT subscription charges. Keep the
# version on persisted estimates so a later table update cannot rewrite history.
# GPT-5.6 Sol's promotional rates apply through at least 2026-11-21.
PRICING_VERSION = "openai-api-2026-09-14-v1"
MODEL_SOURCE_PRICING_VERSION = "model-source-config-v1"
PRICING_SOURCE_URL = "https://developers.openai.com/api/docs/pricing"
PRICING_AS_OF = "2026-09-14"


@dataclass(frozen=True)
class ModelPrice:
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None = None
    priority_multiplier: float | None = None
    priority_input_per_1m: float | None = None
    priority_output_per_1m: float | None = None
    priority_cached_input_per_1m: float | None = None
    flex_input_per_1m: float | None = None
    flex_output_per_1m: float | None = None
    flex_cached_input_per_1m: float | None = None
    long_context_threshold_tokens: float | None = None
    long_context_input_per_1m: float | None = None
    long_context_output_per_1m: float | None = None
    long_context_cached_input_per_1m: float | None = None
    cache_write_multiplier: float | None = None
    priority_long_context: bool = False
    image_input_per_1m: float | None = None
    image_cached_input_per_1m: float | None = None
    text_output_per_1m: float | None = None


@dataclass(frozen=True)
class UsageTokens:
    input_tokens: float
    output_tokens: float
    cached_input_tokens: float = 0.0
    cache_write_tokens: float = 0.0
    image_input_tokens: float | None = None
    cached_image_input_tokens: float | None = None
    text_output_tokens: float | None = None


@dataclass(frozen=True)
class UsageCostBreakdown:
    input_usd: float | None
    cached_input_usd: float | None
    output_usd: float | None
    total_usd: float | None
    cache_write_usd: float | None = None


@dataclass(frozen=True)
class CostItem:
    model: str
    usage: UsageTokens
    service_tier: str | None = None


def _detail_number(details: Mapping[str, JsonValue] | None, name: str) -> float | None:
    value = details.get(name) if details else None
    return _as_number(value) if isinstance(value, (int, float)) else None


def image_usage_tokens(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    input_tokens_details: Mapping[str, JsonValue] | None = None,
    output_tokens_details: Mapping[str, JsonValue] | None = None,
) -> UsageTokens | None:
    """Preserve image usage partitions without guessing missing modality counts."""
    if input_tokens is None or output_tokens is None or input_tokens < 0 or output_tokens < 0:
        return None
    image_input = _detail_number(input_tokens_details, "image_tokens")
    text_input = _detail_number(input_tokens_details, "text_tokens")
    if image_input is not None and text_input is not None and image_input + text_input != input_tokens:
        return None
    if image_input is None and text_input is not None:
        image_input = input_tokens - text_input
    cached = _detail_number(input_tokens_details, "cached_tokens") or 0.0
    cached_details = input_tokens_details.get("cached_tokens_details") if input_tokens_details else None
    cached_image = None
    if isinstance(cached_details, dict):
        cached_image = _detail_number(cached_details, "image_tokens")
        cached_text = _detail_number(cached_details, "text_tokens")
        if cached_image is not None and cached_text is not None and cached_image + cached_text != cached:
            return None
        if cached_image is None and cached_text is not None:
            cached_image = cached - cached_text
    text_output = _detail_number(output_tokens_details, "text_tokens")
    image_output = _detail_number(output_tokens_details, "image_tokens")
    if text_output is not None and image_output is not None and text_output + image_output != output_tokens:
        return None
    if text_output is None and image_output is not None:
        text_output = output_tokens - image_output
    return UsageTokens(
        input_tokens=float(input_tokens),
        output_tokens=float(output_tokens),
        cached_input_tokens=cached,
        image_input_tokens=image_input,
        cached_image_input_tokens=cached_image,
        text_output_tokens=text_output,
    )


def _as_number(value: int | float | None) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if isfinite(number) else None
    return None


def _normalize_usage(usage: UsageTokens | ResponseUsage | None) -> UsageTokens | None:
    if isinstance(usage, UsageTokens):
        input_tokens = _as_number(usage.input_tokens)
        output_tokens = _as_number(usage.output_tokens)
        cached_tokens = _as_number(usage.cached_input_tokens)
        if input_tokens is None or output_tokens is None:
            return None
        input_tokens = max(0.0, input_tokens)
        output_tokens = max(0.0, output_tokens)
        cached_tokens = max(0.0, min(cached_tokens or 0.0, input_tokens))
        write_tokens = max(0.0, min(_as_number(usage.cache_write_tokens) or 0.0, input_tokens - cached_tokens))
        return UsageTokens(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_tokens,
            cache_write_tokens=write_tokens,
            image_input_tokens=usage.image_input_tokens,
            cached_image_input_tokens=usage.cached_image_input_tokens,
            text_output_tokens=usage.text_output_tokens,
        )
    if not usage:
        return None
    input_tokens = _as_number(usage.input_tokens)
    output_tokens = _as_number(usage.output_tokens)
    if output_tokens is None and usage.output_tokens_details is not None:
        output_tokens = _as_number(usage.output_tokens_details.reasoning_tokens)
    if input_tokens is None or output_tokens is None:
        return None
    input_tokens = max(0.0, input_tokens)
    output_tokens = max(0.0, output_tokens)
    cached_tokens = 0.0
    write_tokens = 0.0
    if usage.input_tokens_details is not None:
        cached_tokens = _as_number(usage.input_tokens_details.cached_tokens) or 0.0
        write_tokens = _as_number(usage.input_tokens_details.cache_write_tokens) or 0.0
    cached_tokens = max(0.0, min(cached_tokens, input_tokens))
    write_tokens = max(0.0, min(write_tokens, input_tokens - cached_tokens))
    return UsageTokens(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_tokens,
        cache_write_tokens=write_tokens,
    )


DEFAULT_PRICING_MODELS: dict[str, ModelPrice] = {
    "gpt-6-astra": ModelPrice(
        input_per_1m=10.0,
        cached_input_per_1m=1.0,
        output_per_1m=50.0,
        priority_input_per_1m=20.0,
        priority_cached_input_per_1m=2.0,
        priority_output_per_1m=100.0,
        flex_input_per_1m=5.0,
        flex_cached_input_per_1m=0.5,
        flex_output_per_1m=25.0,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m=20.0,
        long_context_cached_input_per_1m=2.0,
        long_context_output_per_1m=75.0,
        cache_write_multiplier=1.25,
        priority_long_context=True,
    ),
    "gpt-5.6-sol": ModelPrice(
        input_per_1m=4.0,
        cached_input_per_1m=0.4,
        output_per_1m=20.0,
        priority_input_per_1m=8.0,
        priority_cached_input_per_1m=0.8,
        priority_output_per_1m=40.0,
        flex_input_per_1m=2.0,
        flex_cached_input_per_1m=0.2,
        flex_output_per_1m=10.0,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m=8.0,
        long_context_cached_input_per_1m=0.8,
        long_context_output_per_1m=30.0,
        cache_write_multiplier=1.25,
        priority_long_context=True,
    ),
    "gpt-5.6-terra": ModelPrice(
        input_per_1m=2.0,
        cached_input_per_1m=0.2,
        output_per_1m=12.0,
        priority_input_per_1m=4.0,
        priority_cached_input_per_1m=0.4,
        priority_output_per_1m=24.0,
        flex_input_per_1m=1.0,
        flex_cached_input_per_1m=0.1,
        flex_output_per_1m=6.0,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m=4.0,
        long_context_cached_input_per_1m=0.4,
        long_context_output_per_1m=18.0,
        cache_write_multiplier=1.25,
        priority_long_context=True,
    ),
    "gpt-5.6-luna": ModelPrice(
        input_per_1m=0.2,
        cached_input_per_1m=0.02,
        output_per_1m=1.2,
        priority_input_per_1m=0.4,
        priority_cached_input_per_1m=0.04,
        priority_output_per_1m=2.4,
        flex_input_per_1m=0.1,
        flex_cached_input_per_1m=0.01,
        flex_output_per_1m=0.6,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m=0.4,
        long_context_cached_input_per_1m=0.04,
        long_context_output_per_1m=1.8,
        cache_write_multiplier=1.25,
        priority_long_context=True,
    ),
    "gpt-5.5": ModelPrice(
        input_per_1m=5.0,
        cached_input_per_1m=0.5,
        output_per_1m=30.0,
        flex_input_per_1m=2.5,
        flex_cached_input_per_1m=0.25,
        flex_output_per_1m=15.0,
        priority_input_per_1m=12.5,
        priority_cached_input_per_1m=1.25,
        priority_output_per_1m=75.0,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m=10.0,
        long_context_cached_input_per_1m=1.0,
        long_context_output_per_1m=45.0,
    ),
    "gpt-5.5-pro": ModelPrice(
        input_per_1m=30.0,
        output_per_1m=180.0,
        flex_input_per_1m=15.0,
        flex_output_per_1m=90.0,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m=60.0,
        long_context_output_per_1m=270.0,
    ),
    "gpt-5.4": ModelPrice(
        input_per_1m=2.5,
        cached_input_per_1m=0.25,
        output_per_1m=15.0,
        priority_input_per_1m=5.0,
        priority_cached_input_per_1m=0.5,
        priority_output_per_1m=30.0,
        flex_input_per_1m=1.25,
        flex_cached_input_per_1m=0.125,
        flex_output_per_1m=7.5,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m=5.0,
        long_context_cached_input_per_1m=0.5,
        long_context_output_per_1m=22.5,
    ),
    "gpt-5.4-mini": ModelPrice(
        input_per_1m=0.75,
        cached_input_per_1m=0.075,
        output_per_1m=4.5,
        priority_input_per_1m=1.5,
        priority_cached_input_per_1m=0.15,
        priority_output_per_1m=9.0,
        flex_input_per_1m=0.375,
        flex_cached_input_per_1m=0.0375,
        flex_output_per_1m=2.25,
    ),
    "gpt-5.4-nano": ModelPrice(
        input_per_1m=0.20,
        cached_input_per_1m=0.02,
        output_per_1m=1.25,
        flex_input_per_1m=0.10,
        flex_cached_input_per_1m=0.01,
        flex_output_per_1m=0.625,
    ),
    "gpt-5.4-pro": ModelPrice(
        input_per_1m=30.0,
        output_per_1m=180.0,
        flex_input_per_1m=15.0,
        flex_output_per_1m=90.0,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m=60.0,
        long_context_output_per_1m=270.0,
    ),
    "gpt-5.3-codex": ModelPrice(
        input_per_1m=1.75,
        cached_input_per_1m=0.175,
        output_per_1m=14.0,
        priority_input_per_1m=3.5,
        priority_cached_input_per_1m=0.35,
        priority_output_per_1m=28.0,
    ),
    "gpt-5.3": ModelPrice(
        input_per_1m=1.75,
        cached_input_per_1m=0.175,
        output_per_1m=14.0,
    ),
    "gpt-5.3-chat-latest": ModelPrice(
        input_per_1m=1.75,
        cached_input_per_1m=0.175,
        output_per_1m=14.0,
    ),
    "gpt-5.2": ModelPrice(
        input_per_1m=1.75,
        cached_input_per_1m=0.175,
        output_per_1m=14.0,
        priority_multiplier=2.0,
        flex_input_per_1m=0.875,
        flex_cached_input_per_1m=0.0875,
        flex_output_per_1m=7.0,
    ),
    "gpt-5.2-chat-latest": ModelPrice(
        input_per_1m=1.75,
        cached_input_per_1m=0.175,
        output_per_1m=14.0,
    ),
    "gpt-5.1": ModelPrice(
        input_per_1m=1.25,
        cached_input_per_1m=0.125,
        output_per_1m=10.0,
        priority_multiplier=2.0,
        flex_input_per_1m=0.625,
        flex_cached_input_per_1m=0.0625,
        flex_output_per_1m=5.0,
    ),
    "gpt-5.1-chat-latest": ModelPrice(
        input_per_1m=1.25,
        cached_input_per_1m=0.125,
        output_per_1m=10.0,
    ),
    "gpt-5": ModelPrice(
        input_per_1m=1.25,
        cached_input_per_1m=0.125,
        output_per_1m=10.0,
        priority_multiplier=2.0,
        flex_input_per_1m=0.625,
        flex_cached_input_per_1m=0.0625,
        flex_output_per_1m=5.0,
    ),
    "gpt-5-chat-latest": ModelPrice(
        input_per_1m=1.25,
        cached_input_per_1m=0.125,
        output_per_1m=10.0,
    ),
    "gpt-5.2-codex": ModelPrice(
        input_per_1m=1.75,
        cached_input_per_1m=0.175,
        output_per_1m=14.0,
        priority_input_per_1m=3.5,
        priority_cached_input_per_1m=0.35,
        priority_output_per_1m=28.0,
    ),
    "gpt-5.1-codex-max": ModelPrice(
        input_per_1m=1.25,
        cached_input_per_1m=0.125,
        output_per_1m=10.0,
        priority_input_per_1m=2.5,
        priority_cached_input_per_1m=0.25,
        priority_output_per_1m=20.0,
    ),
    "gpt-5.1-codex-mini": ModelPrice(
        input_per_1m=0.25,
        cached_input_per_1m=0.025,
        output_per_1m=2.0,
    ),
    "gpt-5.1-codex": ModelPrice(
        input_per_1m=1.25,
        cached_input_per_1m=0.125,
        output_per_1m=10.0,
        priority_input_per_1m=2.5,
        priority_cached_input_per_1m=0.25,
        priority_output_per_1m=20.0,
    ),
    "gpt-5-codex": ModelPrice(
        input_per_1m=1.25,
        cached_input_per_1m=0.125,
        output_per_1m=10.0,
        priority_input_per_1m=2.5,
        priority_cached_input_per_1m=0.25,
        priority_output_per_1m=20.0,
    ),
    # Image models have distinct text/image input prices. A total without
    # the modality breakdown is insufficient to calculate their input cost.
    "gpt-image-2": ModelPrice(
        input_per_1m=5.0,
        cached_input_per_1m=1.25,
        output_per_1m=30.0,
        image_input_per_1m=8.0,
        image_cached_input_per_1m=2.0,
    ),
    "gpt-image-1.5": ModelPrice(
        input_per_1m=5.0,
        cached_input_per_1m=1.25,
        output_per_1m=32.0,
        image_input_per_1m=8.0,
        image_cached_input_per_1m=2.0,
        text_output_per_1m=10.0,
    ),
    "gpt-image-1": ModelPrice(
        input_per_1m=5.0,
        cached_input_per_1m=1.25,
        output_per_1m=40.0,
        image_input_per_1m=10.0,
        image_cached_input_per_1m=2.5,
    ),
    "gpt-image-1-mini": ModelPrice(
        input_per_1m=2.0,
        cached_input_per_1m=0.2,
        output_per_1m=8.0,
        image_input_per_1m=2.5,
        image_cached_input_per_1m=0.25,
    ),
}

DEFAULT_MODEL_ALIASES: dict[str, str] = {
    "gpt-6-astra-20??-??-??": "gpt-6-astra",
    "gpt-5.6": "gpt-5.6-sol",
    "gpt-5.6-sol*": "gpt-5.6-sol",
    "gpt-5.6-terra*": "gpt-5.6-terra",
    "gpt-5.6-luna*": "gpt-5.6-luna",
    "gpt-5.5-pro*": "gpt-5.5-pro",
    "gpt-5.5*": "gpt-5.5",
    "gpt-5.4-pro*": "gpt-5.4-pro",
    "gpt-5.4-mini*": "gpt-5.4-mini",
    "gpt-5.4-nano*": "gpt-5.4-nano",
    "gpt-5.4*": "gpt-5.4",
    "gpt-5.3-codex*": "gpt-5.3-codex",
    "gpt-5.3-chat-latest*": "gpt-5.3-chat-latest",
    "gpt-5.2-codex*": "gpt-5.2-codex",
    "gpt-5.2-chat-latest*": "gpt-5.2-chat-latest",
    "gpt-5.3*": "gpt-5.3",
    "gpt-5.1-chat-latest*": "gpt-5.1-chat-latest",
    "gpt-5.2*": "gpt-5.2",
    "gpt-5-chat-latest*": "gpt-5-chat-latest",
    "gpt-5.1*": "gpt-5.1",
    "gpt-5*": "gpt-5",
    "gpt-5.1-codex-max*": "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini*": "gpt-5.1-codex-mini",
    "gpt-5.1-codex*": "gpt-5.1-codex",
    "gpt-5-codex*": "gpt-5-codex",
    "gpt-image-2*": "gpt-image-2",
    "gpt-image-1.5*": "gpt-image-1.5",
    "gpt-image-1-mini*": "gpt-image-1-mini",
    "gpt-image-1*": "gpt-image-1",
}


def resolve_model_alias(model: str, aliases: Mapping[str, str]) -> str | None:
    if not model:
        return None
    normalized = model.lower()
    matched: list[tuple[int, str]] = []
    for pattern, target in aliases.items():
        if fnmatchcase(normalized, pattern.lower()):
            matched.append((len(pattern), target))
    if not matched:
        return None
    return max(matched, key=lambda item: item[0])[1]


def get_pricing_for_model(
    model: str,
    pricing: Mapping[str, ModelPrice] | None = None,
    aliases: Mapping[str, str] | None = None,
) -> tuple[str, ModelPrice] | None:
    if not model:
        return None
    pricing = pricing or DEFAULT_PRICING_MODELS
    aliases = aliases or DEFAULT_MODEL_ALIASES

    normalized = model.lower()
    for key, value in pricing.items():
        if key.lower() == normalized:
            return key, value

    alias = resolve_model_alias(normalized, aliases)
    if not alias:
        return None
    for key, value in pricing.items():
        if key.lower() == alias.lower():
            return key, value
    return None


def _uses_priority_tier(service_tier: str | None) -> bool:
    normalized = _normalize_service_tier(service_tier)
    if normalized is None:
        return False
    return normalized in {"priority", "fast"}


def _uses_flex_tier(service_tier: str | None) -> bool:
    normalized = _normalize_service_tier(service_tier)
    if normalized is None:
        return False
    return normalized == "flex"


def _normalize_service_tier(service_tier: str | None) -> str | None:
    if service_tier is None:
        return None
    stripped = service_tier.strip().lower()
    return stripped or None


def _effective_rates(
    usage: UsageTokens,
    price: ModelPrice,
    *,
    service_tier: str | None,
) -> tuple[float, float, float]:
    is_long_context = (
        price.long_context_threshold_tokens is not None
        and usage.input_tokens > price.long_context_threshold_tokens
        and price.long_context_input_per_1m is not None
        and price.long_context_output_per_1m is not None
    )
    input_rate = price.input_per_1m
    cached_rate = price.cached_input_per_1m if price.cached_input_per_1m is not None else input_rate
    output_rate = price.output_per_1m

    if _uses_priority_tier(service_tier):
        if price.priority_input_per_1m is not None and price.priority_output_per_1m is not None:
            priority_cached = (
                price.priority_cached_input_per_1m
                if price.priority_cached_input_per_1m is not None
                else price.priority_input_per_1m
            )
            if is_long_context and price.priority_long_context:
                return price.priority_input_per_1m * 2.0, priority_cached * 2.0, price.priority_output_per_1m * 1.5
            return price.priority_input_per_1m, priority_cached, price.priority_output_per_1m
        if price.priority_multiplier is not None:
            input_rate *= price.priority_multiplier
            cached_rate *= price.priority_multiplier
            output_rate *= price.priority_multiplier
            return input_rate, cached_rate, output_rate

    if _uses_flex_tier(service_tier) and price.flex_input_per_1m is not None and price.flex_output_per_1m is not None:
        input_rate = price.flex_input_per_1m
        cached_rate = price.flex_cached_input_per_1m if price.flex_cached_input_per_1m is not None else input_rate
        output_rate = price.flex_output_per_1m
        if is_long_context:
            input_rate *= 2.0
            cached_rate *= 2.0
            output_rate *= 1.5
        return input_rate, cached_rate, output_rate

    if is_long_context:
        assert price.long_context_input_per_1m is not None
        assert price.long_context_output_per_1m is not None
        input_rate = price.long_context_input_per_1m
        cached_rate = (
            price.long_context_cached_input_per_1m if price.long_context_cached_input_per_1m is not None else input_rate
        )
        output_rate = price.long_context_output_per_1m

    return input_rate, cached_rate, output_rate


def calculate_cost_from_usage(
    usage: UsageTokens | ResponseUsage | None,
    price: ModelPrice,
    *,
    service_tier: str | None = None,
) -> float | None:
    breakdown = calculate_cost_breakdown_from_usage(usage, price, service_tier=service_tier)
    if breakdown is None:
        return None
    return breakdown.total_usd


def _image_cost_components(usage: UsageTokens, price: ModelPrice) -> tuple[float, float, float] | None:
    assert price.image_input_per_1m is not None
    image_input = _as_number(usage.image_input_tokens)
    if image_input is None:
        if usage.input_tokens != 0:
            return None
        image_input = 0.0
    if not 0 <= image_input <= usage.input_tokens or usage.cache_write_tokens:
        return None
    text_input = usage.input_tokens - image_input
    cached_image = _as_number(usage.cached_image_input_tokens)
    if cached_image is None:
        if usage.cached_input_tokens == 0 or image_input == 0:
            cached_image = 0.0
        elif text_input == 0:
            cached_image = usage.cached_input_tokens
        else:
            return None
    if (
        not max(0.0, usage.cached_input_tokens - text_input)
        <= cached_image
        <= min(image_input, usage.cached_input_tokens)
    ):
        return None
    cached_text = usage.cached_input_tokens - cached_image
    text_output = 0.0
    if price.text_output_per_1m is None and usage.text_output_tokens not in (None, 0.0):
        return None
    if price.text_output_per_1m is not None and usage.output_tokens:
        reported_text_output = _as_number(usage.text_output_tokens)
        if reported_text_output is None or not 0 <= reported_text_output <= usage.output_tokens:
            return None
        text_output = reported_text_output
    text_cached_rate = price.cached_input_per_1m if price.cached_input_per_1m is not None else price.input_per_1m
    image_cached_rate = (
        price.image_cached_input_per_1m if price.image_cached_input_per_1m is not None else price.image_input_per_1m
    )
    return (
        ((text_input - cached_text) * price.input_per_1m + (image_input - cached_image) * price.image_input_per_1m)
        / 1_000_000,
        (cached_text * text_cached_rate + cached_image * image_cached_rate) / 1_000_000,
        ((usage.output_tokens - text_output) * price.output_per_1m + text_output * (price.text_output_per_1m or 0.0))
        / 1_000_000,
    )


def calculate_cost_breakdown_from_usage(
    usage: UsageTokens | ResponseUsage | None,
    price: ModelPrice,
    *,
    service_tier: str | None = None,
    precision: int | None = None,
) -> UsageCostBreakdown | None:
    normalized = _normalize_usage(usage)
    if not normalized:
        return None
    billable_input = max(0.0, normalized.input_tokens - normalized.cached_input_tokens - normalized.cache_write_tokens)

    input_rate, cached_rate, output_rate = _effective_rates(
        normalized,
        price,
        service_tier=service_tier,
    )

    input_usd = (billable_input / 1_000_000) * input_rate
    cached_input_usd = (normalized.cached_input_tokens / 1_000_000) * cached_rate
    output_usd = (normalized.output_tokens / 1_000_000) * output_rate
    cache_write_usd = (normalized.cache_write_tokens / 1_000_000) * input_rate * (price.cache_write_multiplier or 1.0)

    if price.image_input_per_1m is not None:
        image_cost = _image_cost_components(normalized, price)
        if image_cost is None:
            return None
        input_usd, cached_input_usd, output_usd = image_cost

    if precision is not None:
        input_usd = round(input_usd, precision)
        cached_input_usd = round(cached_input_usd, precision)
        output_usd = round(output_usd, precision)
        cache_write_usd = round(cache_write_usd, precision)

    total_usd = input_usd + cached_input_usd + output_usd + cache_write_usd

    if precision is not None:
        total_usd = round(total_usd, precision)

    return UsageCostBreakdown(
        input_usd=input_usd,
        cached_input_usd=cached_input_usd,
        output_usd=output_usd,
        total_usd=total_usd,
        cache_write_usd=cache_write_usd,
    )


def calculate_costs(
    items: Iterable[CostItem],
    pricing: Mapping[str, ModelPrice] | None = None,
    aliases: Mapping[str, str] | None = None,
) -> UsageCostSummary:
    pricing = pricing or DEFAULT_PRICING_MODELS
    aliases = aliases or DEFAULT_MODEL_ALIASES

    totals: dict[str, float] = defaultdict(float)
    total_usd = 0.0

    for item in items:
        model = item.model
        usage = item.usage
        resolved = get_pricing_for_model(model, pricing, aliases)
        if not resolved:
            continue
        canonical, price = resolved
        cost = calculate_cost_from_usage(usage, price, service_tier=item.service_tier)
        if cost is None:
            continue
        totals[canonical] += cost
        total_usd += cost

    by_model = [UsageCostByModel(model=model, usd=round(value, 6)) for model, value in sorted(totals.items())]
    return UsageCostSummary(
        currency="USD",
        total_usd_7d=round(total_usd, 6),
        by_model=by_model,
    )
