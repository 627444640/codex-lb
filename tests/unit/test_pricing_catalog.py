from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.core.types import JsonValue
from app.core.usage import pricing_catalog as catalog
from app.core.usage.pricing import ModelPrice, UsageTokens, calculate_cost_from_usage, get_pricing_for_model


@pytest.fixture(autouse=True)
def isolated_catalog(monkeypatch):
    monkeypatch.setattr(catalog, "_prices", None)


def models_dev(cost=None):
    return {
        "openai": {
            "models": {
                "gpt-test": {
                    "modalities": {"output": ["text"]},
                    "cost": cost or {"input": 10, "output": 50, "cache_read": 1},
                }
            }
        }
    }


def test_models_dev_units_context_threshold_and_priority():
    data = models_dev(
        {
            "input": 10,
            "output": 50,
            "cache_read": 1,
            "tiers": [{"tier": {"type": "context", "size": 272000}, "input": 20, "output": 75, "cache_read": 2}],
        }
    )
    data["openai"]["models"]["gpt-test"]["experimental"] = {
        "modes": {
            "fast": {
                "cost": {"input": 20, "output": 100, "cache_read": 2},
                "provider": {"body": {"service_tier": "priority"}},
            }
        }
    }
    price = catalog.parse_models_dev(data)["gpt-test"]
    assert price.long_context_threshold_tokens == 272000
    assert price.priority_output_per_1m == 100
    assert calculate_cost_from_usage(UsageTokens(300000, 1000, 100000), price) == 4.275


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "10"])
def test_invalid_source_cannot_install_prices(bad):
    with pytest.raises(ValueError):
        catalog.parse_models_dev(models_dev({"input": bad, "output": 50}))


def test_litellm_units_and_non_openai_filter():
    entry = {
        "litellm_provider": "openai",
        "mode": "chat",
        "input_cost_per_token": 1e-5,
        "output_cost_per_token": 5e-5,
        "cache_read_input_token_cost": 1e-6,
        "input_cost_per_token_priority": 2e-5,
        "output_cost_per_token_priority": 1e-4,
    }
    prices = catalog.parse_litellm(
        {"gpt-test": entry, "azure/gpt-test": entry, "foreign": {**entry, "litellm_provider": "bedrock"}}
    )
    assert set(prices) == {"gpt-test"}
    assert prices["gpt-test"].input_per_1m == 10
    assert prices["gpt-test"].priority_output_per_1m == 100


def test_supplement_only_when_base_prices_agree():
    primary = ModelPrice(10, 50, 1)
    secondary = replace(primary, flex_input_per_1m=5, flex_output_per_1m=25)
    assert catalog.merge_catalogs({"m": primary}, {"m": secondary})["m"] == secondary
    changed = replace(primary, input_per_1m=12)
    assert catalog.merge_catalogs({"m": changed}, {"m": secondary})["m"] == secondary
    complete = replace(secondary, input_per_1m=12, flex_input_per_1m=6)
    assert catalog.merge_catalogs({"m": complete}, {"m": secondary})["m"] == complete


@pytest.mark.parametrize("tier, expected", [(None, 4.275), ("priority", 8.55), ("fast", 8.55), ("flex", 2.1375)])
def test_astra_prices_include_long_context_tiers(tier, expected):
    catalog.install_prices(
        {
            "gpt-6-astra": ModelPrice(
                10,
                50,
                1,
                long_context_threshold_tokens=272000,
                long_context_input_per_1m=20,
                long_context_output_per_1m=75,
                long_context_cached_input_per_1m=2,
                priority_input_per_1m=20,
                priority_output_per_1m=100,
                priority_cached_input_per_1m=2,
                priority_long_context_input_per_1m=40,
                priority_long_context_output_per_1m=150,
                priority_long_context_cached_input_per_1m=4,
                flex_input_per_1m=5,
                flex_output_per_1m=25,
                flex_cached_input_per_1m=0.5,
                flex_long_context_input_per_1m=10,
                flex_long_context_output_per_1m=37.5,
                flex_long_context_cached_input_per_1m=1,
            )
        }
    )
    resolved = get_pricing_for_model("gpt-6-astra-2026-09-04")
    assert resolved is not None
    assert resolved[0] == "gpt-6-astra"
    assert calculate_cost_from_usage(UsageTokens(300000, 1000, 100000), resolved[1], service_tier=tier) == expected


def test_new_dated_model_beats_legacy_gpt5_wildcard():
    catalog.install_prices({"gpt-5.99": ModelPrice(17, 80)})
    assert get_pricing_for_model("gpt-5.99-2026-09-10") == ("gpt-5.99", ModelPrice(17, 80))
    sol = get_pricing_for_model("gpt-5.6")
    assert sol is not None
    assert sol[0] == "gpt-5.6-sol"


def test_snapshot_round_trip_and_partial_refresh_preserves_missing_models():
    prices = catalog.decode_snapshot(json.loads(catalog.BUNDLE_PATH.read_text()))
    assert catalog.decode_snapshot(json.loads(catalog.encode_snapshot(prices))) == prices
    catalog.install_prices({"gpt-test": ModelPrice(1, 2)})
    catalog.install_prices({"gpt-other": ModelPrice(2, 3)})
    assert get_pricing_for_model("gpt-test") == ("gpt-test", ModelPrice(1, 2))


def test_unlisted_gpt5_family_stays_missing_until_pricing_arrives():
    assert get_pricing_for_model("gpt-5.99") is None
    catalog.install_prices({"gpt-5.99": ModelPrice(17, 80)})
    assert get_pricing_for_model("gpt-5.99") == ("gpt-5.99", ModelPrice(17, 80))


def test_partial_source_outage_retains_compatible_tier_prices():
    complete = ModelPrice(10, 50, 1, flex_input_per_1m=5, flex_output_per_1m=25)
    catalog.install_prices({"gpt-test": complete})
    catalog.install_prices({"gpt-test": ModelPrice(10, 50, 1)})
    assert get_pricing_for_model("gpt-test") == ("gpt-test", complete)


def test_conflicting_priority_rate_cannot_borrow_long_context_rates():
    primary = ModelPrice(10, 50, 1, priority_input_per_1m=25, priority_output_per_1m=125)
    secondary = replace(
        primary,
        priority_input_per_1m=20,
        priority_output_per_1m=100,
        long_context_threshold_tokens=272000,
        priority_long_context_input_per_1m=40,
        priority_long_context_output_per_1m=150,
    )
    assert catalog.merge_catalogs({"m": primary}, {"m": secondary})["m"] == secondary


def test_bundled_snapshot_covers_astra_without_network():
    prices = catalog.decode_snapshot(json.loads(catalog.BUNDLE_PATH.read_text()))
    assert "gpt-6-astra" in prices
    assert get_pricing_for_model("gpt-6-astra") == ("gpt-6-astra", prices["gpt-6-astra"])


@pytest.mark.parametrize("tier", ["priority", "flex"])
def test_litellm_tier_only_long_context_rates_are_used(tier):
    entry = {
        "litellm_provider": "openai",
        "mode": "chat",
        "input_cost_per_token": 1e-5,
        "output_cost_per_token": 5e-5,
        "cache_read_input_token_cost": 1e-6,
        f"input_cost_per_token_{tier}": 2e-5,
        f"output_cost_per_token_{tier}": 1e-4,
        f"cache_read_input_token_cost_{tier}": 2e-6,
        f"input_cost_per_token_above_272k_tokens_{tier}": 4e-5,
        f"output_cost_per_token_above_272k_tokens_{tier}": 1.5e-4,
        f"cache_read_input_token_cost_above_272k_tokens_{tier}": 4e-6,
    }
    price = catalog.parse_litellm({"gpt-test": entry})["gpt-test"]
    assert price.long_context_input_per_1m is None
    assert calculate_cost_from_usage(UsageTokens(300000, 1000, 100000), price, service_tier=tier) == 8.55
    assert calculate_cost_from_usage(UsageTokens(272000, 1000, 100000), price, service_tier=tier) == pytest.approx(3.74)
    assert calculate_cost_from_usage(UsageTokens(300000, 1000, 100000), price) is None
    # Another tier's long-context group cannot trigger guessed multipliers for this tier.
    other = "flex" if tier == "priority" else "priority"
    ordinary = replace(price, **{f"{other}_input_per_1m": 2, f"{other}_output_per_1m": 4})
    assert calculate_cost_from_usage(UsageTokens(300000, 1000, 100000), ordinary, service_tier=other) is None


@pytest.mark.parametrize("prefix", ["long_context_", "priority_long_context_", "flex_long_context_"])
@pytest.mark.parametrize("threshold", [None, 0])
def test_snapshot_rejects_long_context_rates_without_positive_threshold(prefix, threshold):
    values = {"input_per_1m": 10, "output_per_1m": 50, prefix + "input_per_1m": 20, prefix + "output_per_1m": 100}
    if threshold is not None:
        values["long_context_threshold_tokens"] = threshold
    with pytest.raises(ValueError, match="Missing context threshold"):
        catalog.decode_snapshot({"schema_version": 1, "models": {"gpt-test": values}})


def test_models_dev_carries_cache_write_evidence_and_explicit_mode_context():
    data = models_dev({"input": 10, "output": 50, "cache_read": 1, "cache_write": 12.5})
    data["openai"]["models"]["gpt-test"]["experimental"] = {
        "modes": {
            "fast": {
                "provider": {"body": {"service_tier": "priority"}},
                "cost": {
                    "input": 20,
                    "output": 100,
                    "cache_read": 2,
                    "cache_write": 25,
                    "tiers": [
                        {
                            "tier": {"type": "context", "size": 272000},
                            "input": 40,
                            "output": 150,
                            "cache_read": 4,
                            "cache_write": 50,
                        }
                    ],
                },
            }
        }
    }
    price = catalog.parse_models_dev(data)["gpt-test"]
    assert price.cache_write_multiplier == 1.25
    assert price.priority_long_context_input_per_1m == 40
    assert calculate_cost_from_usage(UsageTokens(300000, 1000, 100000, 50000), price, service_tier="priority") == 9.05
    assert calculate_cost_from_usage(UsageTokens(300000, 1000), price) is None


@pytest.mark.parametrize("tier_write", [26, True, -1, float("inf")])
def test_models_dev_rejects_unrepresentable_cache_write_evidence(tier_write):
    data = models_dev({"input": 10, "output": 50, "cache_read": 1, "cache_write": 12.5})
    data["openai"]["models"]["gpt-test"]["experimental"] = {
        "modes": {
            "fast": {
                "provider": {"body": {"service_tier": "priority"}},
                "cost": {"input": 20, "output": 100, "cache_write": tier_write},
            }
        }
    }
    with pytest.raises(ValueError, match="no valid"):
        catalog.parse_models_dev(data)


def test_litellm_carries_explicit_cache_creation_prices():
    entry = {
        "litellm_provider": "openai",
        "mode": "chat",
        "input_cost_per_token": 1e-5,
        "output_cost_per_token": 5e-5,
        "cache_creation_input_token_cost": 1.25e-5,
        "input_cost_per_token_flex": 5e-6,
        "output_cost_per_token_flex": 2.5e-5,
        "cache_creation_input_token_cost_flex": 6.25e-6,
    }
    price = catalog.parse_litellm({"gpt-test": entry})["gpt-test"]
    assert price.cache_write_multiplier == 1.25
    assert calculate_cost_from_usage(UsageTokens(100, 10, 0, 40), price, service_tier="flex") == pytest.approx(0.0008)


@pytest.mark.parametrize(
    "model", ["gpt-5.3", "gpt-5.3-codex-spark", "codex-auto-review", "gpt-5.3-codex-spark-2026-09-17"]
)
def test_known_unpriced_models_cannot_reenter_from_parsers_snapshots_or_install(model):
    entry = {"input_per_1m": 1, "output_per_1m": 2}
    snapshot = {"schema_version": 1, "models": {"gpt-valid": entry, model: entry}}
    assert model not in catalog.decode_snapshot(snapshot)
    data = models_dev()
    data["openai"]["models"][model] = data["openai"]["models"]["gpt-test"]
    assert model not in catalog.parse_models_dev(data)
    raw = {"litellm_provider": "openai", "mode": "chat", "input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6}
    assert model not in catalog.parse_litellm({"gpt-valid": raw, model: raw})
    catalog.install_prices({model: ModelPrice(1, 2)})
    assert get_pricing_for_model(model) is None
    assert (
        model
        not in json.loads(catalog.encode_snapshot({"gpt-valid": ModelPrice(1, 2), model: ModelPrice(1, 2)}))["models"]
    )


@pytest.mark.parametrize("alias", ["gpt-5.6", "gpt-daybreak-blue-latest", "daybreak-blue-latest"])
def test_stale_catalog_alias_price_cannot_override_canonical_model(alias):
    catalog.install_prices({alias: ModelPrice(999, 999)})
    assert get_pricing_for_model(alias) == get_pricing_for_model("gpt-5.6-sol")


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-image-2"])
def test_partial_refresh_cannot_erase_cache_write_or_image_pricing(model):
    from app.core.usage.pricing import get_pricing_version

    resolved = get_pricing_for_model(model)
    assert resolved is not None
    before = resolved[1]
    version = get_pricing_version(model)
    partial = ModelPrice(before.input_per_1m * 2, before.output_per_1m, before.cached_input_per_1m)
    catalog.install_prices({model: partial})
    assert get_pricing_for_model(model) == resolved
    assert get_pricing_version(model) == version
    updated = replace(before, input_per_1m=before.input_per_1m * 2)
    catalog.install_prices({model: updated})
    assert get_pricing_for_model(model) == (model, updated)
    assert get_pricing_version(model) != version


def test_effective_price_version_tracks_its_rates_without_unrelated_refresh_churn():
    from app.core.usage.pricing import get_pricing_version

    price = ModelPrice(10, 50, 1, cache_write_multiplier=1.25)
    catalog.install_prices({"gpt-test": price})
    version = get_pricing_version("gpt-test")
    assert version == get_pricing_version(price=replace(price, input_per_1m=10.0))
    catalog_version = get_pricing_version("unknown-model")
    catalog.install_prices({"gpt-other": ModelPrice(1, 2)})
    assert get_pricing_version("gpt-test") == version
    assert get_pricing_version("unknown-model") != catalog_version
    catalog.install_prices({"gpt-test": replace(price, cache_write_multiplier=1.5)})
    assert get_pricing_version("gpt-test") != version
    assert get_pricing_version(price=price) == version  # A captured rate cannot change during settlement.


def test_snapshot_v2_preserves_every_supported_accounting_field():
    from app.core.usage.pricing import DEFAULT_PRICING_MODELS

    selected = {model: DEFAULT_PRICING_MODELS[model] for model in ("gpt-6-astra", "gpt-image-2", "gpt-image-1")}
    snapshot = json.loads(catalog.encode_snapshot(selected))
    assert snapshot["schema_version"] == 2
    assert catalog.decode_snapshot(snapshot) == selected
    for field in ("cache_write_multiplier", "image_input_per_1m", "priority_long_context_input_per_1m"):
        with pytest.raises(ValueError, match="Invalid price"):
            catalog.decode_snapshot(
                {"schema_version": 2, "models": {"gpt-test": {"input_per_1m": 1, "output_per_1m": 2, field: True}}}
            )


def test_catalog_text_tier_does_not_imply_image_modality_tier_prices():
    from app.core.usage.pricing import has_pricing_for_usage

    resolved = get_pricing_for_model("gpt-image-2")
    assert resolved is not None
    promoted = replace(resolved[1], priority_input_per_1m=10, priority_output_per_1m=60)
    assert not has_pricing_for_usage(UsageTokens(100, 10), promoted, service_tier="priority")


def test_unrepresentable_cache_write_ratio_rejects_source_record():
    with pytest.raises(ValueError, match="no valid"):
        catalog.parse_models_dev(models_dev({"input": 1e-308, "output": 50, "cache_write": 1e308}))


def test_catalog_model_case_does_not_bypass_active_price_precedence():
    price = ModelPrice(3, 9)
    catalog.install_prices({"GPT-TEST": price})
    assert get_pricing_for_model("gpt-test-2026-09-17") == ("gpt-test", price)


@pytest.mark.parametrize(
    ("model", "expected_long_cost"),
    [("gpt-5.5", 3.045), ("gpt-5.4", 1.5225), ("gpt-5.5-pro", 18.27)],
)
def test_same_base_partial_refresh_retains_all_tiers_and_context(model: str, expected_long_cost: float):
    from app.core.usage.pricing import get_pricing_version

    resolved = get_pricing_for_model(model)
    assert resolved is not None
    before = resolved[1]
    version = get_pricing_version(model)
    cost: dict[str, JsonValue] = {"input": before.input_per_1m, "output": before.output_per_1m}
    if before.cached_input_per_1m is not None:
        cost["cache_read"] = before.cached_input_per_1m
    payload: JsonValue = {"openai": {"models": {model: {"modalities": {"output": ["text"]}, "cost": cost}}}}
    catalog.install_prices(catalog.parse_models_dev(payload))
    after = get_pricing_for_model(model)
    assert after == resolved
    assert get_pricing_version(model) == version
    assert calculate_cost_from_usage(UsageTokens(300000, 1000), after[1]) == pytest.approx(expected_long_cost)
    for tier in ("priority", "flex"):
        usage = UsageTokens(100, 10)
        assert calculate_cost_from_usage(usage, after[1], service_tier=tier) == calculate_cost_from_usage(
            usage, before, service_tier=tier
        )


@pytest.mark.parametrize("conflict", ["base", "threshold", "priority"])
def test_incompatible_partial_refresh_retains_complete_record_but_complete_update_replaces(conflict):
    from app.core.usage.pricing import get_pricing_version

    model = "gpt-5.5"
    resolved = get_pricing_for_model(model)
    assert resolved is not None
    before = resolved[1]
    changes = {
        "base": {"input_per_1m": 6.0},
        "threshold": {"long_context_threshold_tokens": 200000.0},
        "priority": {"priority_input_per_1m": 14.0, "priority_output_per_1m": 80.0},
    }[conflict]
    partial = replace(ModelPrice(before.input_per_1m, before.output_per_1m, before.cached_input_per_1m), **changes)
    version = get_pricing_version(model)
    catalog.install_prices({model: partial})
    assert get_pricing_for_model(model) == resolved
    assert get_pricing_version(model) == version
    complete = replace(before, **changes)
    catalog.install_prices({model: complete})
    assert get_pricing_for_model(model) == (model, complete)
    assert get_pricing_version(model) != version


def test_compatible_partial_refresh_adds_explicit_priority_context_without_erasing_existing_groups():
    resolved = get_pricing_for_model("gpt-5.5")
    assert resolved is not None
    before = resolved[1]
    explicit = ModelPrice(
        before.input_per_1m,
        before.output_per_1m,
        before.cached_input_per_1m,
        long_context_threshold_tokens=272000,
        priority_long_context_input_per_1m=22,
        priority_long_context_output_per_1m=137,
        priority_long_context_cached_input_per_1m=2.2,
    )
    catalog.install_prices({"gpt-5.5": explicit})
    after = get_pricing_for_model("gpt-5.5")
    assert after is not None
    assert after[1].long_context_input_per_1m == before.long_context_input_per_1m
    assert after[1].flex_input_per_1m == before.flex_input_per_1m
    assert after[1].priority_input_per_1m == before.priority_input_per_1m
    assert calculate_cost_from_usage(UsageTokens(300000, 1000), after[1], service_tier="priority") == pytest.approx(
        6.737
    )


def test_complete_explicit_priority_quote_replaces_legacy_multiplier_when_base_changes():
    legacy = ModelPrice(1, 10, 0.1, priority_multiplier=2)
    updated = ModelPrice(
        2, 12, 0.2, priority_input_per_1m=4, priority_output_per_1m=24, priority_cached_input_per_1m=0.4
    )
    catalog.install_prices({"gpt-test": legacy})
    catalog.install_prices({"gpt-test": updated})
    assert get_pricing_for_model("gpt-test") == ("gpt-test", updated)
    assert calculate_cost_from_usage(
        UsageTokens(100000, 1000, 10000), updated, service_tier="priority"
    ) == pytest.approx(0.388)


def test_compatible_explicit_priority_partial_keeps_cached_multiplier_evidence_and_version():
    from app.core.usage.pricing import get_pricing_version

    legacy = ModelPrice(1, 10, 0.1, priority_multiplier=2)
    catalog.install_prices({"gpt-test": legacy})
    version = get_pricing_version("gpt-test")
    partial = ModelPrice(1, 10, 0.1, priority_input_per_1m=2, priority_output_per_1m=20)
    catalog.install_prices({"gpt-test": partial})
    assert get_pricing_for_model("gpt-test") == ("gpt-test", legacy)
    assert get_pricing_version("gpt-test") == version


def test_incompatible_multiplier_partial_cannot_override_cached_explicit_priority_group():
    old = ModelPrice(
        1,
        10,
        0.1,
        priority_input_per_1m=3,
        priority_output_per_1m=30,
        priority_cached_input_per_1m=0.3,
        flex_input_per_1m=0.5,
        flex_output_per_1m=5,
        flex_cached_input_per_1m=0.05,
    )
    partial = ModelPrice(1, 10, 0.1, priority_multiplier=2)
    assert catalog.merge_catalogs({"m": partial}, {"m": old})["m"] == old
