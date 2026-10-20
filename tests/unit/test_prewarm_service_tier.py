from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.openai.model_registry import ModelRegistry, UpstreamModel
from app.core.openai.requests import ResponsesRequest
from app.modules.proxy.request_policy import apply_prewarm_service_tier_model_fallback

pytestmark = pytest.mark.unit


def _model() -> UpstreamModel:
    return UpstreamModel(
        slug="gpt-5.6-luna",
        display_name="Luna",
        description="test",
        context_window=128000,
        input_modalities=("text",),
        supported_reasoning_levels=(),
        default_reasoning_level=None,
        supports_reasoning_summaries=False,
        support_verbosity=False,
        default_verbosity=None,
        prefer_websockets=True,
        supports_parallel_tool_calls=True,
        supported_in_api=True,
        minimal_client_version=None,
        priority=0,
        available_in_plans=frozenset({"pro"}),
        raw={"service_tiers": [{"id": "priority"}]},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "generate", "tier", "expected"),
    [
        ("prewarm", False, "flex", None),
        ("prewarm", True, "flex", "flex"),
        ("prewarm", None, "flex", "flex"),
        ("prewarm", 0, "flex", "flex"),
        ("prewarm", "false", "flex", "flex"),
        ("normal", False, "flex", "flex"),
        ("prewarm", False, "priority", "priority"),
        ("prewarm", False, "ultrafast", "ultrafast"),
        ("prewarm", False, None, None),
    ],
)
async def test_prewarm_flex_requires_literal_no_generation(kind, generate, tier, expected):
    model = _model()
    registry = ModelRegistry(ttl_seconds=60)
    await registry.update({"pro": [model]}, per_account_results={"account": ("pro", [model])})
    request = ResponsesRequest.model_validate(
        {
            "model": model.slug,
            "instructions": "",
            "input": [],
            "service_tier": tier,
            "generate": generate,
        }
    )
    changed = apply_prewarm_service_tier_model_fallback(request, request_kind=kind, registry=registry)
    assert request.service_tier == expected
    assert changed is (tier == "flex" and expected is None)
    assert request.to_payload().get("generate") == generate


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["advertised", "unknown-model", "no-snapshot", "partial-catalog", "metadata-only"])
async def test_prewarm_flex_preserves_supported_or_uncertain_catalog(state):
    model = _model()
    if state == "advertised":
        model = replace(model, raw={"service_tiers": [{"id": "flex"}]})
    registry = ModelRegistry(ttl_seconds=60)
    if state != "no-snapshot":
        accounts = {"account": ("pro", [model])}
        active_plans = {"account": "pro", "unknown": "pro"} if state == "partial-catalog" else None
        await registry.update({"pro": [model]}, per_account_results=accounts, active_account_plans=active_plans)
        if state == "metadata-only":
            await registry.update({"pro": []}, per_account_results={"account": ("pro", [])})
    request = ResponsesRequest.model_validate(
        {
            "model": "unknown-source-model" if state == "unknown-model" else model.slug,
            "instructions": "",
            "input": [],
            "service_tier": "flex",
            "generate": False,
        }
    )
    assert apply_prewarm_service_tier_model_fallback(request, request_kind="prewarm", registry=registry) is False
    assert request.to_payload()["service_tier"] == "flex"
