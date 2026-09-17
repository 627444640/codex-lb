from __future__ import annotations

import pytest
from sqlalchemy import select

import app.modules.proxy.service as proxy_module
from app.core.usage.pricing import UsageTokens, calculate_cost_from_usage, get_pricing_for_model, get_pricing_version
from app.db.models import RequestLog
from app.db.session import SessionLocal
from tests.integration.test_proxy_images import _disable_http_bridge as _disable_http_bridge
from tests.integration.test_proxy_images import _import_account, _sse

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["response.completed", "response.failed", "response.incomplete"])
@pytest.mark.parametrize("first_terminal", [False, True])
async def test_terminal_usage_survives_error_and_prices_actual_model(
    async_client, app_instance, monkeypatch, terminal, first_terminal
):
    await _import_account(async_client, "usage-terminal", "usage-terminal@example.invalid")
    response_id = "usage-" + terminal
    usage = {
        "input_tokens": 100,
        "output_tokens": 30,
        "total_tokens": 130,
        "input_tokens_details": {"cached_tokens": 40, "cache_write_tokens": 20},
        "output_tokens_details": {"reasoning_tokens": 20},
    }

    async def fake_stream(*args, **kwargs):
        if not first_terminal:
            yield _sse({"type": "response.created", "response": {"id": response_id, "status": "in_progress"}})
            yield _sse({"type": "response.output_text.delta", "response_id": response_id, "delta": "sample"})
        response = {
            "id": response_id,
            "status": terminal.split(".")[1],
            "model": "gpt-5.4-mini",
            "usage": usage,
        }
        if terminal == "response.failed":
            response["error"] = {"code": "invalid_request_error", "message": "synthetic failure"}
        if terminal == "response.incomplete":
            response["incomplete_details"] = {"reason": "max_output_tokens"}
        yield _sse({"type": terminal, "response": response})

    async def fresh(self, account, **kwargs):
        return account

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)
    monkeypatch.setattr(proxy_module.ProxyService, "_ensure_fresh_with_budget", fresh)
    response = await async_client.post(
        "/backend-api/codex/responses",
        json={"model": "gpt-5.4", "instructions": "audit", "input": [], "stream": True},
    )
    assert response.status_code == 200
    await app_instance.state.proxy_service.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog))).scalars().one()
        assert (row.input_tokens, row.output_tokens, row.cached_input_tokens, row.reasoning_tokens) == (100, 30, 40, 20)
        assert row.cache_write_tokens == 20
        assert row.model == "gpt-5.4"
        assert row.actual_model == "gpt-5.4-mini"
        assert row.pricing_version == get_pricing_version(row.actual_model or row.model)
        resolved = get_pricing_for_model("gpt-5.4-mini", None, None)
        assert resolved is not None
        assert row.cost_usd == calculate_cost_from_usage(UsageTokens(100, 30, 40, 20), resolved[1])
        assert row.status == ("success" if terminal == "response.completed" else "error")


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["generations", "edits"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("image_usage_kind", ["known", "missing_modality", "missing"])
async def test_image_request_log_replaces_host_tokens_and_cost(
    async_client, app_instance, monkeypatch, route, stream, image_usage_kind
):
    await _import_account(async_client, "usage-image", "usage-image@example.invalid")
    image_usage = {"input_tokens": 7, "output_tokens": 13}
    if image_usage_kind == "known":
        image_usage["input_tokens_details"] = {"image_tokens": 5, "text_tokens": 2, "cached_tokens": 0}

    async def fake_stream(*args, **kwargs):
        yield _sse(
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {"type": "image_generation_call", "id": "ig_usage", "status": "completed", "result": "b64"},
            }
        )
        response = {
            "id": "resp_image_usage",
            "object": "response",
            "status": "completed",
            "model": "gpt-5.5",
            "usage": {"input_tokens": 100, "output_tokens": 30, "output_tokens_details": {"reasoning_tokens": 20}},
        }
        if image_usage_kind != "missing":
            response["tool_usage"] = {"image_gen": image_usage}
        yield _sse({"type": "response.completed", "response": response})

    async def fresh(self, account, **kwargs):
        return account

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)
    monkeypatch.setattr(proxy_module.ProxyService, "_ensure_fresh_with_budget", fresh)
    if route == "generations":
        response = await async_client.post(
            "/v1/images/generations", json={"model": "gpt-image-2", "prompt": "synthetic", "stream": stream}
        )
    else:
        response = await async_client.post(
            "/v1/images/edits",
            data={"model": "gpt-image-2", "prompt": "synthetic", "stream": str(stream).lower()},
            files={"image": ("source.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "image/png")},
        )
    assert response.status_code == 200, response.text
    if not stream and image_usage_kind != "missing":
        assert response.json()["usage"]["input_tokens"] == 7
        assert response.json()["usage"]["output_tokens"] == 13
    await app_instance.state.proxy_service.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog))).scalars().one()
        assert row.model == "gpt-image-2"
        assert row.actual_model is None
        assert row.reasoning_tokens is None
        assert row.pricing_version == get_pricing_version(row.actual_model or row.model)
        assert (row.input_tokens, row.output_tokens) == ((None, None) if image_usage_kind == "missing" else (7, 13))
        if image_usage_kind == "known":
            # GPT Image 2: 2 text inputs at $5/M, 5 image inputs at $8/M, 13 image outputs at $30/M.
            assert row.cost_usd == pytest.approx(0.00044)
        else:
            assert row.cost_usd is None


@pytest.mark.asyncio
async def test_invalid_new_usage_metadata_preserves_legacy_usage(async_client, app_instance, monkeypatch):
    await _import_account(async_client, "usage-invalid", "usage-invalid@example.invalid")

    async def fake_stream(*args, **kwargs):
        yield _sse(
            {
                "type": "response.completed",
                "response": {
                    "id": "metadata-invalid",
                    "model": {"invalid": "object"},
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "input_tokens_details": {"cached_tokens": 3, "cache_write_tokens": "invalid"},
                    },
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)
    response = await async_client.post(
        "/backend-api/codex/responses", json={"model": "gpt-5.4", "input": [], "stream": True}
    )
    assert response.status_code == 200
    await app_instance.state.proxy_service.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog))).scalars().one()
        assert (row.input_tokens, row.output_tokens, row.cached_input_tokens) == (10, 2, 3)
        assert row.cache_write_tokens is None
        assert row.actual_model is None


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["response.completed", "response.failed", "response.incomplete"])
@pytest.mark.parametrize("transport", ["http", "websocket"])
async def test_websocket_and_bridge_terminal_accounting(async_client, app_instance, terminal, transport):
    import asyncio
    import time

    from app.core.openai.models import OpenAIEvent
    from app.db.models import Account

    await _import_account(async_client, "usage-websocket", "usage-websocket@example.invalid")
    async with SessionLocal() as session:
        account = (await session.execute(select(Account))).scalars().one()
    payload = {
        "type": terminal,
        "response": {
            "id": "usage-websocket-terminal",
            "model": "gpt-5.4-mini",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 30,
                "input_tokens_details": {"cached_tokens": 40, "cache_write_tokens": 20},
            },
        },
    }
    state = proxy_module._WebSocketRequestState(
        request_id="usage-websocket-request",
        model="gpt-5.4",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=time.monotonic(),
        transport=transport,
    )
    from app.dependencies import get_proxy_service_for_app

    service = get_proxy_service_for_app(app_instance)
    await service._finalize_websocket_request_state(
        state,
        account=account,
        account_id_value=account.id,
        event=OpenAIEvent.model_validate(payload),
        event_type=terminal,
        payload=payload,
        api_key=None,
        upstream_control=proxy_module._WebSocketUpstreamControl(),
        response_create_gate=asyncio.Semaphore(1),
    )
    await service.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog))).scalars().one()
        assert row.model == "gpt-5.4"
        assert row.actual_model == "gpt-5.4-mini"
        assert (row.input_tokens, row.output_tokens, row.cached_input_tokens, row.cache_write_tokens) == (
            100,
            30,
            40,
            20,
        )
        assert row.transport == transport
        assert row.status == ("success" if terminal == "response.completed" else "error")


@pytest.mark.asyncio
async def test_compact_terminal_accounting(async_client, app_instance, monkeypatch):
    from app.core.openai.models import CompactResponsePayload

    await _import_account(async_client, "usage-compact", "usage-compact@example.invalid")

    async def fake_compact(*args, **kwargs):
        return CompactResponsePayload.model_validate(
            {
                "id": "usage-compact-result",
                "object": "response.compact",
                "model": "gpt-5.4-mini",
                "output": [],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 30,
                    "input_tokens_details": {
                        "cached_tokens": 40,
                        "cache_write_tokens": 20,
                    },
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)
    response = await async_client.post(
        "/backend-api/codex/responses/compact", json={"model": "gpt-5.4", "instructions": "audit", "input": []}
    )
    assert response.status_code == 200, response.text
    await app_instance.state.proxy_service.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog))).scalars().one()
        assert row.model == "gpt-5.4"
        assert row.actual_model == "gpt-5.4-mini"
        assert (row.input_tokens, row.output_tokens, row.cached_input_tokens, row.cache_write_tokens) == (
            100,
            30,
            40,
            20,
        )


@pytest.mark.asyncio
async def test_warmup_captures_usage_metadata(async_client, app_instance, monkeypatch):
    from app.core.openai.models import CompactResponsePayload
    from app.db.models import Account
    from app.dependencies import get_proxy_service_for_app
    from app.modules.proxy._service.warmup import _snapshot_warmup_account

    await _import_account(async_client, "usage-warmup", "usage-warmup@example.invalid")
    async with SessionLocal() as session:
        account = (await session.execute(select(Account))).scalars().one()

    async def fake_compact(*args, **kwargs):
        return CompactResponsePayload.model_validate(
            {
                "id": "usage-warmup-result",
                "object": "response.compact",
                "model": "gpt-5.4-mini",
                "output": [],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 30,
                    "input_tokens_details": {
                        "cached_tokens": 40,
                        "cache_write_tokens": 20,
                    },
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)
    service = get_proxy_service_for_app(app_instance)
    result = await service._submit_warmup_request(
        account=_snapshot_warmup_account(account),
        headers={},
        api_key=None,
        warmup_model="gpt-5.4",
        prohibit_fast_mode=False,
    )
    assert result.success
    await service.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog))).scalars().one()
        assert row.request_kind == "warmup"
        assert row.actual_model == "gpt-5.4-mini"
        assert (row.input_tokens, row.output_tokens, row.cached_input_tokens, row.cache_write_tokens) == (
            100,
            30,
            40,
            20,
        )
