"""Public catalog adapters; only validated OpenAI text-token prices enter accounting."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from app.core.types import JsonValue
from app.core.usage.pricing import DEFAULT_PRICING_MODELS, ModelPrice, is_catalog_model_allowed

logger = logging.getLogger(__name__)
MODELS_DEV_URL = "https://models.dev/api.json"
LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
BUNDLE_PATH = Path(__file__).with_name("pricing_snapshot.json")
_FIELDS = {field.name for field in fields(ModelPrice)}
MAX_CATALOG_BYTES = 16 * 1024 * 1024


def _object(value: JsonValue) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def _rates(data: dict[str, JsonValue], names: dict[str, str], scale: float = 1.0) -> dict[str, float]:
    result: dict[str, float] = {}
    for source, target in names.items():
        value = data.get(source)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid price field: {source}")
        scaled = float(value) * scale
        if not math.isfinite(scaled):
            raise ValueError(f"Invalid scaled price: {source}")
        result[target] = scaled
    return result


def _price(values: dict[str, float]) -> ModelPrice:
    if not {"input_per_1m", "output_per_1m"} <= values.keys():
        raise ValueError("Incomplete base prices")
    for prefix in ("priority_", "flex_", "long_context_", "priority_long_context_", "flex_long_context_"):
        group = {prefix + part + "_per_1m" for part in ("input", "output")}
        present = (group | {prefix + "cached_input_per_1m"}) & values.keys()
        if present and not group <= values.keys():
            raise ValueError("Incomplete tier prices")
        if present and "long_context_" in prefix and values.get("long_context_threshold_tokens", 0) <= 0:
            raise ValueError("Missing context threshold")
    return ModelPrice(**values)


def _cache_write_multiplier(
    values: dict[str, float], data: dict[str, JsonValue], field: str, *, prefix: str = "", scale: float = 1.0
) -> None:
    writes = _rates(data, {field: "write"}, scale)
    if not writes:
        return
    input_rate = values.get(prefix + "input_per_1m")
    if input_rate is None or input_rate <= 0:
        raise ValueError("Cache-write price requires a positive input rate")
    multiplier = writes["write"] / input_rate
    if not math.isfinite(multiplier):
        raise ValueError("Invalid cache-write multiplier")
    previous = values.get("cache_write_multiplier")
    if prefix and previous is None:
        raise ValueError("Tier-only cache-write multiplier is unsupported")
    if previous is not None and not math.isclose(previous, multiplier, rel_tol=1e-6):
        raise ValueError("Inconsistent cache-write multipliers")
    values["cache_write_multiplier"] = multiplier


def _context_rates(
    values: dict[str, float], cost: dict[str, JsonValue], names: dict[str, str], *, prefix: str = ""
) -> None:
    tiers = cost.get("tiers", [])
    if not isinstance(tiers, list) or len(tiers) > 1:
        raise ValueError("Unsupported context tiers")
    if not tiers:
        if cost.get("context_over_200k") is not None:
            raise ValueError("Context tier lacks an explicit threshold")
        return
    tier = _object(tiers[0])
    descriptor = _object(tier.get("tier"))
    if descriptor.get("type") != "context":
        raise ValueError("Unsupported price tier")
    threshold = _rates(descriptor, {"size": "long_context_threshold_tokens"})
    existing_threshold = values.get("long_context_threshold_tokens")
    if existing_threshold is not None and threshold.get("long_context_threshold_tokens") != existing_threshold:
        raise ValueError("Inconsistent context thresholds")
    values.update(threshold)
    context_prefix = prefix + "long_context_"
    values.update(_rates(tier, {key: context_prefix + value for key, value in names.items()}))
    _cache_write_multiplier(values, tier, "cache_write", prefix=context_prefix)


def parse_models_dev(payload: JsonValue) -> dict[str, ModelPrice]:
    models = _object(_object(_object(payload).get("openai")).get("models"))
    result: dict[str, ModelPrice] = {}
    names = {"input": "input_per_1m", "output": "output_per_1m", "cache_read": "cached_input_per_1m"}
    for model, raw in models.items():
        entry = _object(raw)
        # The bare personality alias must keep resolving to the canonical Sol entry.
        if not is_catalog_model_allowed(model) or _object(entry.get("modalities")).get("output") != ["text"]:
            continue
        try:
            cost = _object(entry.get("cost"))
            values = _rates(cost, names)
            _cache_write_multiplier(values, cost, "cache_write")
            _context_rates(values, cost, names)
            modes = _object(_object(entry.get("experimental")).get("modes"))
            for raw_mode in modes.values():
                mode = _object(raw_mode)
                tier_name = _object(_object(mode.get("provider")).get("body")).get("service_tier")
                if tier_name in ("priority", "flex"):
                    mode_cost = _object(mode.get("cost"))
                    values.update(_rates(mode_cost, {k: f"{tier_name}_{v}" for k, v in names.items()}))
                    _cache_write_multiplier(values, mode_cost, "cache_write", prefix=f"{tier_name}_")
                    _context_rates(values, mode_cost, names, prefix=f"{tier_name}_")
            result[model.lower()] = _price(values)
        except (ValueError, OverflowError):
            logger.debug("Ignoring unsupported models.dev price for %s", model)
    if not result:
        raise ValueError("models.dev supplied no valid OpenAI prices")
    return result


def parse_litellm(payload: JsonValue) -> dict[str, ModelPrice]:
    result: dict[str, ModelPrice] = {}
    base = {
        "input_cost_per_token": "input_per_1m",
        "output_cost_per_token": "output_per_1m",
        "cache_read_input_token_cost": "cached_input_per_1m",
    }
    for model, raw in _object(payload).items():
        entry = _object(raw)
        if entry.get("litellm_provider") != "openai" or entry.get("mode") != "chat" or "/" in model:
            continue
        if any(word in model for word in ("audio", "realtime")) or not is_catalog_model_allowed(model):
            continue
        try:
            values = _rates(entry, base, 1_000_000)
            _cache_write_multiplier(values, entry, "cache_creation_input_token_cost", scale=1_000_000)
            for tier in ("priority", "flex"):
                values.update(_rates(entry, {f"{k}_{tier}": f"{tier}_{v}" for k, v in base.items()}, 1_000_000))
                _cache_write_multiplier(
                    values, entry, f"cache_creation_input_token_cost_{tier}", prefix=f"{tier}_", scale=1_000_000
                )
            thresholds = {
                int(key.split("_above_")[1].split("k_tokens")[0]) * 1000
                for key in entry
                if key.startswith("input_cost_per_token_above_") and "k_tokens" in key
            }
            if len(thresholds) > 1:
                raise ValueError("Unsupported multiple thresholds")
            if thresholds:
                threshold = thresholds.pop()
                values["long_context_threshold_tokens"] = float(threshold)
                for tier in ("", "priority", "flex"):
                    suffix = f"_above_{threshold // 1000}k_tokens" + (f"_{tier}" if tier else "")
                    prefix = f"{tier}_long_context_" if tier else "long_context_"
                    values.update(_rates(entry, {k + suffix: prefix + v for k, v in base.items()}, 1_000_000))
                    _cache_write_multiplier(
                        values, entry, "cache_creation_input_token_cost" + suffix, prefix=prefix, scale=1_000_000
                    )
            result[model.lower()] = _price(values)
        except (ValueError, OverflowError):
            logger.debug("Ignoring unsupported LiteLLM price for %s", model)
    if not result:
        raise ValueError("LiteLLM supplied no valid OpenAI prices")
    return result


def _merge_values(price: ModelPrice) -> dict[str, float | None]:
    values: dict[str, float | None] = asdict(price)
    if price.priority_multiplier is not None:
        # A multiplier and an explicit priority triple are alternative
        # representations of the same evidence, not independent requirements.
        if price.priority_input_per_1m is None and price.priority_output_per_1m is None:
            values["priority_input_per_1m"] = price.input_per_1m * price.priority_multiplier
            values["priority_output_per_1m"] = price.output_per_1m * price.priority_multiplier
            cached = price.cached_input_per_1m if price.cached_input_per_1m is not None else price.input_per_1m
            values["priority_cached_input_per_1m"] = cached * price.priority_multiplier
        values["priority_multiplier"] = None
    return values


def _compatible_rate(value: float | None, previous: float | None) -> bool:
    return value is None or previous is None or math.isclose(value, previous, rel_tol=1e-6)


def merge_catalogs(primary: dict[str, ModelPrice], secondary: dict[str, ModelPrice]) -> dict[str, ModelPrice]:
    result = {model.lower(): price for model, price in secondary.items() if is_catalog_model_allowed(model)}
    for model, price in primary.items():
        if not is_catalog_model_allowed(model):
            continue
        model = model.lower()
        other = result.get(model)
        if other is None:
            result[model] = price
            continue
        values = _merge_values(price)
        previous = _merge_values(other)
        missing_evidence = any(value is not None and values[key] is None for key, value in previous.items())
        if not missing_evidence:
            # A complete new record may change base, tier, context or modality
            # rates. Last-good protection must not freeze verified updates.
            result[model] = price
        elif all(_compatible_rate(value, previous[key]) for key, value in values.items()):
            # Absence is not deletion. Compatible partial refreshes inherit all
            # missing evidence together, including thresholds and whole tiers.
            merged = {key: value if value is not None else previous[key] for key, value in values.items()}
            result[model] = (
                other if merged == previous else _price({key: val for key, val in merged.items() if val is not None})
            )
        else:
            # Different base/threshold/tier rates cannot borrow missing groups
            # from an older quote. Retain the last complete record instead.
            logger.debug("Retaining complete pricing evidence for %s after an incomplete refresh", model)
            result[model] = other

    return result


def snapshot_updated_at(payload: JsonValue) -> datetime:
    value = _object(payload).get("updated_at", "1970-01-01T00:00:00+00:00")
    if not isinstance(value, str):
        raise ValueError("Invalid pricing snapshot timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Pricing snapshot timestamp must include timezone")
    return parsed


def decode_snapshot(payload: JsonValue) -> dict[str, ModelPrice]:
    root = _object(payload)
    snapshot_updated_at(payload)
    if root.get("schema_version") not in (1, 2):
        raise ValueError("Unsupported pricing snapshot")
    result = {
        model.lower(): _price(_rates(_object(raw), {key: key for key in _FIELDS}))
        for model, raw in _object(root.get("models")).items()
        if is_catalog_model_allowed(model)
    }
    if not result:
        raise ValueError("Empty pricing snapshot")
    return result


def encode_snapshot(prices: dict[str, ModelPrice]) -> str:
    return (
        json.dumps(
            {
                "schema_version": 2,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "sources": [MODELS_DEV_URL, LITELLM_URL],
                "models": {
                    model: {k: v for k, v in asdict(price).items() if v is not None}
                    for model, price in sorted(prices.items())
                    if is_catalog_model_allowed(model)
                },
            },
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


async def fetch_catalogs() -> dict[str, ModelPrice]:
    catalogs: list[dict[str, ModelPrice]] = []
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=20),
        trust_env=True,
        headers={"User-Agent": "codex-lb", "Accept": "application/json"},
    ) as session:
        for url, parser in ((MODELS_DEV_URL, parse_models_dev), (LITELLM_URL, parse_litellm)):
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        body.extend(chunk)
                        if len(body) > MAX_CATALOG_BYTES:
                            raise ValueError("Pricing response too large")
                    catalogs.append(parser(json.loads(body)))
            except (aiohttp.ClientError, TimeoutError, ValueError):
                logger.warning("Pricing source unavailable: %s", url, exc_info=True)
                catalogs.append({})
    if not any(catalogs):
        raise ValueError("All pricing sources failed")
    return merge_catalogs(catalogs[0], catalogs[1])


_prices: dict[str, ModelPrice] | None = None


def get_active_prices() -> dict[str, ModelPrice]:
    global _prices
    if _prices is None:
        _prices = {**DEFAULT_PRICING_MODELS, **decode_snapshot(json.loads(BUNDLE_PATH.read_text()))}
    return _prices


def install_prices(prices: dict[str, ModelPrice]) -> None:
    global _prices
    _prices = merge_catalogs(prices, get_active_prices())
