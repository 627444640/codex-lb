from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from app.core.types import JsonValue

# Historical provenance identifiers and inert compatibility shapes only.
# The internal distribution contains no price catalogue or cost calculators.
PRICING_VERSION = "openai-api-2026-09-17-v1"
MODEL_SOURCE_PRICING_VERSION = "model-source-config-v1"


def get_pricing_for_model(
    model: str,
    prices: Mapping[str, ModelPrice] | None = None,
    aliases: Mapping[str, str] | None = None,
) -> tuple[str, ModelPrice] | None:
    """Keep immutable historical migrations importable without any price book."""
    return None


def calculate_cost_from_usage(
    usage: UsageTokens | None,
    price: ModelPrice,
    *,
    service_tier: str | None = None,
) -> float | None:
    """Retired migration compatibility entry point; never generate an amount."""
    return None


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
    flex_long_context: bool = False
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
