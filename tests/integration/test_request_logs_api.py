from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.auth.dashboard_access import guest_principal
from app.core.auth.dependencies import validate_dashboard_session
from app.core.crypto import TokenEncryptor
from app.core.utils.time import utcnow
from app.db.models import Account, AccountStatus, ApiKey, ModelSource, RequestLog
from app.db.session import SessionLocal
from app.modules.accounts.repository import AccountsRepository
from app.modules.request_logs.repository import RequestLogsRepository

pytestmark = pytest.mark.integration


def _make_account(account_id: str, email: str) -> Account:
    encryptor = TokenEncryptor()
    return Account(
        id=account_id,
        email=email,
        plan_type="plus",
        access_token_encrypted=encryptor.encrypt("access"),
        refresh_token_encrypted=encryptor.encrypt("refresh"),
        id_token_encrypted=encryptor.encrypt("id"),
        last_refresh=utcnow(),
        status=AccountStatus.ACTIVE,
        deactivation_reason=None,
    )


@pytest.mark.asyncio
async def test_request_logs_api_returns_recent(async_client, db_setup):
    async with SessionLocal() as session:
        accounts_repo = AccountsRepository(session)
        logs_repo = RequestLogsRepository(session)
        await accounts_repo.upsert(_make_account("acc_logs", "logs@example.com"))
        session.add(
            ApiKey(
                id="key_logs_1",
                name="Debug Key",
                key_hash="hash_logs_1",
                key_prefix="sk-test",
            )
        )
        await session.commit()

        now = utcnow()
        await logs_repo.add_log(
            account_id="acc_logs",
            request_id="req_logs_1",
            model="gpt-5.1",
            input_tokens=100,
            output_tokens=200,
            latency_ms=1200,
            status="success",
            error_code=None,
            requested_at=now - timedelta(minutes=1),
            transport="http",
        )
        await logs_repo.add_log(
            account_id="acc_logs",
            request_id="req_logs_2",
            archive_request_id="archive_req_logs_2",
            model="legacy-model",
            input_tokens=50,
            output_tokens=0,
            latency_ms=300,
            status="error",
            error_code="rate_limit_exceeded",
            error_message="Rate limit reached",
            failure_phase="owner_forward_status",
            failure_detail="owner_forward_non_200",
            failure_exception_type="ProxyResponseError",
            upstream_status_code=503,
            upstream_error_code="bridge_owner_forward_failed",
            bridge_stage="owner_forward",
            requested_at=now,
            api_key_id="key_logs_1",
            transport="websocket",
            connection_request_kind="prewarm",
        )

    response = await async_client.get("/api/request-logs?limit=2")
    assert response.status_code == 200
    body = response.json()
    payload = body["requests"]
    assert len(payload) == 2
    assert body["total"] == 2
    assert body["hasMore"] is False

    latest = payload[0]
    assert latest["status"] == "rate_limit"
    assert latest["apiKeyId"] == "key_logs_1"
    assert latest["apiKeyName"] == "Debug Key"
    assert latest["errorCode"] == "rate_limit_exceeded"
    assert latest["requestId"] == "req_logs_2"
    assert latest["archiveRequestId"] == "archive_req_logs_2"
    assert latest["errorMessage"] == "Rate limit reached"
    assert latest["failurePhase"] == "owner_forward_status"
    assert latest["failureDetail"] == "owner_forward_non_200"
    assert latest["failureExceptionType"] == "ProxyResponseError"
    assert latest["upstreamStatusCode"] == 503
    assert latest["upstreamErrorCode"] == "bridge_owner_forward_failed"
    assert latest["bridgeStage"] == "owner_forward"
    assert latest["costBreakdown"] == {
        "inputUsd": None,
        "cachedInputUsd": None,
        "cacheWriteUsd": None,
        "outputUsd": None,
        "totalUsd": None,
    }
    assert latest["transport"] == "websocket"
    assert latest["requestKind"] == "normal"
    assert latest["connectionRequestKind"] == "prewarm"

    older = payload[1]
    assert older["status"] == "ok"
    assert older["requestId"] == "req_logs_1"
    assert older["archiveRequestId"] == "req_logs_1"
    assert older["apiKeyId"] is None
    assert older["apiKeyName"] is None
    assert older["tokens"] == 300
    assert older["inputTokens"] == 100
    assert older["outputTokens"] == 200
    assert older["cachedInputTokens"] is None
    assert older["costBreakdown"] == {
        "inputUsd": None,
        "cachedInputUsd": None,
        "cacheWriteUsd": None,
        "outputUsd": pytest.approx(0.002),
        "totalUsd": pytest.approx(0.002125),
    }
    assert older["transport"] == "http"
    assert older["requestKind"] == "normal"
    assert older["connectionRequestKind"] is None


@pytest.mark.asyncio
async def test_request_logs_api_returns_upstream_proxy_route_metadata(async_client, db_setup):
    del db_setup
    async with SessionLocal() as session:
        logs_repo = RequestLogsRepository(session)
        now = utcnow()
        await logs_repo.add_log(
            account_id=None,
            request_id="req_route_success",
            model="gpt-5.1",
            input_tokens=10,
            output_tokens=20,
            latency_ms=100,
            status="success",
            error_code=None,
            requested_at=now - timedelta(seconds=1),
            upstream_proxy_route_mode="account_bound",
            upstream_proxy_pool_id="pool_route",
            upstream_proxy_endpoint_id="endpoint_route",
            upstream_proxy_fallback_used=True,
        )
        await logs_repo.add_log(
            account_id=None,
            request_id="req_route_fail_closed",
            model="gpt-5.1",
            input_tokens=None,
            output_tokens=None,
            latency_ms=0,
            status="error",
            error_code="upstream_proxy_unavailable",
            requested_at=now,
            upstream_proxy_route_mode="account_bound",
            upstream_proxy_pool_id="pool_route",
            upstream_proxy_fail_closed_reason="no_healthy_endpoint",
        )

    response = await async_client.get("/api/request-logs?limit=2")
    assert response.status_code == 200
    fail_closed, success = response.json()["requests"]
    assert fail_closed["upstreamProxyRouteMode"] == "account_bound"
    assert fail_closed["upstreamProxyPoolId"] == "pool_route"
    assert fail_closed["upstreamProxyEndpointId"] is None
    assert fail_closed["upstreamProxyFallbackUsed"] is None
    assert fail_closed["upstreamProxyFailClosedReason"] == "no_healthy_endpoint"
    assert success["upstreamProxyRouteMode"] == "account_bound"
    assert success["upstreamProxyPoolId"] == "pool_route"
    assert success["upstreamProxyEndpointId"] == "endpoint_route"
    assert success["upstreamProxyFallbackUsed"] is True
    assert success["upstreamProxyFailClosedReason"] is None


@pytest.mark.asyncio
async def test_request_logs_api_returns_model_source_metadata(async_client, db_setup):
    del db_setup
    async with SessionLocal() as session:
        logs_repo = RequestLogsRepository(session)
        await logs_repo.add_log(
            account_id=None,
            model_source_id="source_history",
            model_source_kind="openai_compatible",
            request_id="req_source_history",
            model="source-model",
            input_tokens=10,
            output_tokens=20,
            latency_ms=100,
            status="success",
            error_code=None,
            source="model_source",
        )

    response = await async_client.get("/api/request-logs?limit=1")
    assert response.status_code == 200
    latest = response.json()["requests"][0]
    assert latest["requestId"] == "req_source_history"
    assert latest["source"] == "model_source"
    assert latest["modelSourceId"] == "source_history"
    assert latest["modelSourceKind"] == "openai_compatible"


@pytest.mark.asyncio
async def test_request_log_model_source_id_survives_source_delete(db_setup):
    del db_setup
    async with SessionLocal() as session:
        session.add(
            ModelSource(
                id="source_deleted_history",
                name="deleted history",
                base_url="https://deleted-history.example.invalid/v1",
            )
        )
        await session.commit()
        logs_repo = RequestLogsRepository(session)
        saved = await logs_repo.add_log(
            account_id=None,
            model_source_id="source_deleted_history",
            model_source_kind="openai_compatible",
            request_id="req_deleted_source_history",
            model="source-model",
            input_tokens=10,
            output_tokens=20,
            latency_ms=100,
            status="success",
            error_code=None,
            source="model_source",
        )
        source = await session.get(ModelSource, "source_deleted_history")
        assert source is not None
        await session.delete(source)
        await session.commit()

        persisted = await session.get(RequestLog, saved.id)
        assert persisted is not None
        assert persisted.model_source_id == "source_deleted_history"
        assert persisted.model_source_kind == "openai_compatible"


@pytest.mark.asyncio
async def test_request_logs_api_returns_useragent_fields(async_client, db_setup):
    async with SessionLocal() as session:
        accounts_repo = AccountsRepository(session)
        logs_repo = RequestLogsRepository(session)
        await accounts_repo.upsert(_make_account("acc_logs_useragent", "ua-logs@example.com"))

        now = utcnow()
        await logs_repo.add_log(
            account_id="acc_logs_useragent",
            request_id="req_logs_useragent_present",
            model="gpt-5.1",
            input_tokens=10,
            output_tokens=20,
            latency_ms=100,
            status="success",
            error_code=None,
            requested_at=now,
            useragent="opencode/1.15.13 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14",
            useragent_group="opencode",
            client_ip="203.0.113.7",
        )
        await logs_repo.add_log(
            account_id="acc_logs_useragent",
            request_id="req_logs_useragent_absent",
            model="gpt-5.1-mini",
            input_tokens=5,
            output_tokens=15,
            latency_ms=50,
            status="success",
            error_code=None,
            requested_at=now - timedelta(minutes=1),
        )

    response = await async_client.get("/api/request-logs?limit=2")
    assert response.status_code == 200
    payload = response.json()["requests"]
    assert [entry["requestId"] for entry in payload] == [
        "req_logs_useragent_present",
        "req_logs_useragent_absent",
    ]

    latest = payload[0]
    assert latest["useragent"] == "opencode/1.15.13 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14"
    assert latest["useragentGroup"] == "opencode"
    assert latest["clientIp"] == "203.0.113.7"

    older = payload[1]
    assert older["useragent"] is None
    assert older["useragentGroup"] is None
    assert older["clientIp"] is None


@pytest.mark.asyncio
async def test_request_logs_api_redacts_sensitive_metadata_for_guest_and_preserves_admin(
    app_instance,
    async_client,
    db_setup,
):
    del db_setup
    async with SessionLocal() as session:
        logs_repo = RequestLogsRepository(session)
        await logs_repo.add_log(
            account_id=None,
            request_id="req_guest_visible",
            archive_request_id="archive_guest_hidden",
            conversation_id="conversation_guest_hidden",
            model="gpt-5.1",
            input_tokens=100,
            output_tokens=20,
            latency_ms=250,
            status="success",
            error_code=None,
            useragent="codex-cli/1.2.3 runtime/node",
            useragent_group="codex-cli",
            client_ip="203.0.113.17",
        )

    app_instance.dependency_overrides[validate_dashboard_session] = guest_principal
    try:
        guest_response = await async_client.get("/api/request-logs?limit=1")
    finally:
        app_instance.dependency_overrides.pop(validate_dashboard_session, None)

    assert guest_response.status_code == 200
    guest_entry = guest_response.json()["requests"][0]
    assert guest_entry["requestId"] == "req_guest_visible"
    assert guest_entry["archiveRequestId"] is None
    assert guest_entry["conversationId"] is None
    assert guest_entry["useragent"] is None
    assert guest_entry["clientIp"] is None
    assert guest_entry["useragentGroup"] == "codex-cli"
    assert guest_entry["model"] == "gpt-5.1"
    assert guest_entry["status"] == "ok"
    assert guest_entry["tokens"] == 120
    assert guest_entry["latencyMs"] == 250

    admin_response = await async_client.get("/api/request-logs?limit=1")
    assert admin_response.status_code == 200
    admin_entry = admin_response.json()["requests"][0]
    assert admin_entry["archiveRequestId"] == "archive_guest_hidden"
    assert admin_entry["conversationId"] == "conversation_guest_hidden"
    assert admin_entry["useragent"] == "codex-cli/1.2.3 runtime/node"
    assert admin_entry["clientIp"] == "203.0.113.17"


@pytest.mark.asyncio
async def test_request_logs_api_excludes_client_ip_from_guest_search_and_preserves_admin_search(
    app_instance,
    async_client,
    db_setup,
    monkeypatch,
):
    from app.modules.request_logs import repository as logs_repository_module

    del db_setup
    monkeypatch.setattr(logs_repository_module, "_COUNT_CACHE_TTL_SECONDS", 30.0)
    logs_repository_module._clear_recent_count_cache()
    async with SessionLocal() as session:
        logs_repo = RequestLogsRepository(session)
        await logs_repo.add_log(
            account_id=None,
            request_id="req_ip_search_target",
            model="gpt-5.1",
            input_tokens=100,
            output_tokens=20,
            latency_ms=250,
            status="success",
            error_code=None,
            client_ip="203.0.113.17",
        )

    try:
        app_instance.dependency_overrides[validate_dashboard_session] = guest_principal
        try:
            guest_response = await async_client.get("/api/request-logs?search=203.0.113")
        finally:
            app_instance.dependency_overrides.pop(validate_dashboard_session, None)

        assert guest_response.status_code == 200
        assert guest_response.json()["requests"] == []
        assert guest_response.json()["total"] == 0

        admin_response = await async_client.get("/api/request-logs?search=203.0.113")
        assert admin_response.status_code == 200
        assert [entry["requestId"] for entry in admin_response.json()["requests"]] == [
            "req_ip_search_target",
        ]
        assert admin_response.json()["total"] == 1
    finally:
        logs_repository_module._clear_recent_count_cache()


@pytest.mark.asyncio
async def test_request_logs_api_rejects_guest_conversation_filter_and_preserves_admin_aggregates(
    app_instance,
    async_client,
    db_setup,
):
    del db_setup
    async with SessionLocal() as session:
        logs_repo = RequestLogsRepository(session)
        await logs_repo.add_log(
            account_id=None,
            request_id="req_conversation_filter_target",
            conversation_id="conversation-filter-target",
            model="gpt-5.1",
            input_tokens=100,
            output_tokens=20,
            latency_ms=250,
            status="success",
            error_code=None,
            cost_usd=4.25,
        )

    app_instance.dependency_overrides[validate_dashboard_session] = guest_principal
    try:
        guest_response = await async_client.get(
            "/api/request-logs",
            params={"conversation_id": "conversation-filter-target"},
        )
    finally:
        app_instance.dependency_overrides.pop(validate_dashboard_session, None)

    assert guest_response.status_code == 403
    assert guest_response.json()["error"]["code"] == "permission_required"

    admin_response = await async_client.get(
        "/api/request-logs",
        params={"conversation_id": "conversation-filter-target"},
    )
    assert admin_response.status_code == 200
    admin_payload = admin_response.json()
    assert [entry["requestId"] for entry in admin_payload["requests"]] == [
        "req_conversation_filter_target",
    ]
    assert admin_payload["total"] == 1
    assert admin_payload["conversation"] == {
        "requestCount": 1,
        "aggregatedCostUsd": 4.25,
    }


@pytest.mark.asyncio
async def test_request_logs_api_lists_limit_warmup_rows(async_client, db_setup):
    async with SessionLocal() as session:
        accounts_repo = AccountsRepository(session)
        logs_repo = RequestLogsRepository(session)
        await accounts_repo.upsert(_make_account("acc_warmup_logs", "warmup-logs@example.com"))

        await logs_repo.add_log(
            account_id="acc_warmup_logs",
            request_id="req_normal_traffic",
            model="gpt-5.2",
            input_tokens=100,
            output_tokens=100,
            latency_ms=100,
            status="success",
            error_code=None,
            plan_type="plus",
        )
        await logs_repo.add_log(
            account_id="acc_warmup_logs",
            request_id="req_limit_warmup",
            model="gpt-5.1-codex-mini",
            input_tokens=1,
            output_tokens=1,
            latency_ms=10,
            status="success",
            error_code=None,
            plan_type="plus",
            request_kind="warmup",
        )

    response = await async_client.get("/api/request-logs?limit=10")
    assert response.status_code == 200
    body = response.json()
    request_ids = [entry["requestId"] for entry in body["requests"]]
    assert request_ids == ["req_limit_warmup", "req_normal_traffic"]
    assert body["requests"][0]["requestKind"] == "warmup"
    assert body["requests"][1]["requestKind"] == "normal"
    assert body["total"] == 2

    options_response = await async_client.get("/api/request-logs/options")
    assert options_response.status_code == 200
    option_models = [entry["model"] for entry in options_response.json()["modelOptions"]]
    assert "gpt-5.1-codex-mini" in option_models


@pytest.mark.asyncio
async def test_request_log_total_count_is_cached_per_filter_signature(async_client, db_setup, monkeypatch):
    """With the TTL enabled, repeated listings reuse the cached COUNT(*) for
    the same filter signature; distinct signatures count separately."""
    from sqlalchemy import event

    from app.db.session import engine
    from app.modules.request_logs import repository as logs_repository_module

    monkeypatch.setattr(logs_repository_module, "_COUNT_CACHE_TTL_SECONDS", 30.0)
    logs_repository_module._clear_recent_count_cache()

    count_statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT COUNT") and "request_logs" in statement:
            count_statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    try:
        first = await async_client.get("/api/request-logs?limit=5")
        second = await async_client.get("/api/request-logs?limit=5&offset=5")
        filtered = await async_client.get("/api/request-logs?limit=5&status=ok")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _capture)
        logs_repository_module._clear_recent_count_cache()

    assert first.status_code == 200
    assert second.status_code == 200
    assert filtered.status_code == 200
    assert first.json()["total"] == second.json()["total"]
    # One COUNT for the shared default signature (page 2 reuses it), one for
    # the status-filtered signature.
    assert len(count_statements) == 2


@pytest.mark.asyncio
async def test_request_logs_cost_evidence_and_subcent_precision(async_client, db_setup):
    from app.core.usage.pricing import get_pricing_version

    async with SessionLocal() as session:
        repo = RequestLogsRepository(session)
        await repo.add_log(
            account_id=None,
            latency_ms=1,
            status="success",
            error_code=None,
            request_id="cost-current",
            model="gpt-5.4",
            actual_model="gpt-5.6-luna",
            input_tokens=16280,
            cached_input_tokens=15104,
            cache_write_tokens=100,
            output_tokens=63,
        )
        await repo.add_log(
            account_id=None,
            latency_ms=1,
            status="success",
            error_code=None,
            request_id="cost-tiny",
            model="gpt-5.6-luna",
            input_tokens=1,
            cached_input_tokens=1,
            cache_write_tokens=0,
            output_tokens=0,
        )
        await repo.add_log(
            account_id=None,
            latency_ms=1,
            status="success",
            error_code=None,
            request_id="cost-unknown",
            model="codex-auto-review",
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=10,
        )
        for request_id, cost, model in (
            ("cost-historical", 0.123456789, "gpt-5.6-sol"),
            ("cost-unrecorded", None, "gpt-6-astra"),
        ):
            session.add(
                RequestLog(
                    request_id=request_id,
                    model=model,
                    input_tokens=100,
                    output_tokens=10,
                    cached_input_tokens=0,
                    status="success",
                    cost_usd=cost,
                )
            )
        await session.commit()

    response = await async_client.get("/api/request-logs?limit=20")
    assert response.status_code == 200
    rows = {row["requestId"]: row for row in response.json()["requests"]}
    row = rows["cost-current"]
    assert row["model"] == "gpt-5.4"
    assert row["actualModel"] == "gpt-5.6-luna"
    assert row["pricingVersion"] == get_pricing_version(row.get("actualModel") or row["model"])
    assert row["cacheWriteTokens"] == 100
    assert row["tokens"] == 16343  # Cached and writes are subsets, not extra tokens.
    assert row["costUsd"] == pytest.approx(0.00061788)
    assert row["costBreakdown"]["cacheWriteUsd"] == pytest.approx(0.000025)
    assert row["costStatus"] == "estimated"
    assert rows["cost-tiny"]["costUsd"] == pytest.approx(0.00000002)
    assert rows["cost-unknown"]["costUsd"] is None
    assert rows["cost-unknown"]["costStatus"] == "unknown_model"
    assert rows["cost-historical"]["costUsd"] == pytest.approx(0.123456789)
    assert rows["cost-historical"]["costStatus"] == "historical"
    assert rows["cost-historical"]["costBreakdown"]["inputUsd"] is None
    assert rows["cost-unrecorded"]["costUsd"] == pytest.approx(0.0015)
    assert rows["cost-unrecorded"]["costStatus"] == "incomplete_usage"
    assert rows["cost-unrecorded"]["cacheWriteTokens"] is None

    # Rendering a current estimate never changes historical accounting storage.
    from sqlalchemy import select

    async with SessionLocal() as session:
        old = await session.scalar(select(RequestLog).where(RequestLog.request_id == "cost-unrecorded"))
        assert old is not None and old.cost_usd is None and old.pricing_version is None


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_pricing_version", [False, True])
async def test_request_logs_preserve_explicit_unknown_image_and_custom_source_provenance(
    async_client, db_setup, previous_pricing_version
):
    from app.core.usage.pricing import MODEL_SOURCE_PRICING_VERSION
    from app.modules.request_logs.repository import RequestLogUsageUpdate

    async with SessionLocal() as session:
        repo = RequestLogsRepository(session)
        await repo.add_log(
            account_id=None,
            latency_ms=1,
            status="success",
            error_code=None,
            request_id="unknown-image-cost",
            model="gpt-5.4",
            input_tokens=0,
            output_tokens=100,
        )
        # Full image evidence could not be priced. The flattened zero-input
        # log would otherwise look priceable without its original modalities.
        assert (
            await repo.update_usage_for_request(
                "unknown-image-cost", "gpt-image-2", RequestLogUsageUpdate(0, 100, 0, None, None, None)
            )
            == 1
        )
        if previous_pricing_version:
            from sqlalchemy import update

            await session.execute(
                update(RequestLog)
                .where(RequestLog.request_id == "unknown-image-cost")
                .values(pricing_version="openai-api-previous")
            )
            await session.commit()
        await repo.add_log(
            account_id=None,
            latency_ms=1,
            status="success",
            error_code=None,
            request_id="source-current-cost",
            model="gpt-5.6-luna",
            model_source_id="synthetic-source",
            input_tokens=0,
            output_tokens=100,
            cost_usd=0.1234567,
        )

    response = await async_client.get("/api/request-logs?limit=20")
    assert response.status_code == 200
    rows = {row["requestId"]: row for row in response.json()["requests"]}
    image = rows["unknown-image-cost"]
    assert image["costUsd"] is None
    assert image["costStatus"] == "incomplete_usage"
    assert all(value is None for value in image["costBreakdown"].values())
    source = rows["source-current-cost"]
    assert source["costUsd"] == pytest.approx(0.1234567)
    assert source["costStatus"] == "estimated"
    assert source["pricingVersion"] == MODEL_SOURCE_PRICING_VERSION
    assert source["costBreakdown"]["inputUsd"] is None


@pytest.mark.asyncio
async def test_corrected_model_prices_persist_without_repricing_history(async_client, db_setup):
    from sqlalchemy import select

    from app.core.usage.pricing import get_pricing_version

    async with SessionLocal() as session:
        repo = RequestLogsRepository(session)
        for model in ("gpt-5-mini", "gpt-5.2-pro", "gpt-5.3-codex-spark", "gpt-5.7"):
            row = await repo.add_log(
                account_id=None,
                latency_ms=1,
                status="success",
                error_code=None,
                request_id=f"corrected-{model}",
                model="gpt-5",
                actual_model=model,
                input_tokens=100_000,
                cached_input_tokens=0,
                cache_write_tokens=0,
                output_tokens=1_000,
            )
            assert row.pricing_version == get_pricing_version(row.actual_model or row.model)
        session.add(
            RequestLog(
                request_id="previous-mini-price",
                model="gpt-5-mini",
                input_tokens=100_000,
                cached_input_tokens=0,
                cache_write_tokens=0,
                output_tokens=1_000,
                status="success",
                cost_usd=0.135,
                pricing_version="openai-api-2026-09-14-v1",
            )
        )
        await session.commit()

    response = await async_client.get("/api/request-logs?limit=20")
    assert response.status_code == 200
    rows = {row["requestId"]: row for row in response.json()["requests"]}
    for model, expected in (("gpt-5-mini", 0.027), ("gpt-5.2-pro", 2.268)):
        row = rows[f"corrected-{model}"]
        assert row["costUsd"] == pytest.approx(expected)
        assert row["costStatus"] == "estimated"
        assert row["pricingVersion"] == get_pricing_version(row.get("actualModel") or row["model"])
    for model in ("gpt-5.3-codex-spark", "gpt-5.7"):
        row = rows[f"corrected-{model}"]
        assert row["costUsd"] is None
        assert row["costStatus"] == "unknown_model"
        assert all(value is None for value in row["costBreakdown"].values())
    historical = rows["previous-mini-price"]
    assert historical["costUsd"] == pytest.approx(0.135)
    assert historical["pricingVersion"] == "openai-api-2026-09-14-v1"
    assert historical["costStatus"] == "historical"
    assert historical["costBreakdown"]["inputUsd"] is None

    async with SessionLocal() as session:
        saved = {row.request_id: row for row in (await session.scalars(select(RequestLog))).all()}
        assert saved["corrected-gpt-5-mini"].cost_usd == pytest.approx(0.027)
        assert saved["corrected-gpt-5.2-pro"].cost_usd == pytest.approx(2.268)
        assert saved["corrected-gpt-5.3-codex-spark"].cost_usd is None
        assert saved["corrected-gpt-5.7"].cost_usd is None
        assert saved["previous-mini-price"].cost_usd == pytest.approx(0.135)
        assert saved["previous-mini-price"].pricing_version == "openai-api-2026-09-14-v1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "service_tier", "input_tokens"),
    [("gpt-5.6-sol", "ultrafast", 100_000), ("gpt-5.5-pro", "flex", 272_001)],
)
async def test_request_logs_keep_unpublished_tier_and_context_prices_unknown(
    async_client, db_setup, model, service_tier, input_tokens
):
    from sqlalchemy import select

    from app.core.usage.pricing import get_pricing_version

    async with SessionLocal() as session:
        await RequestLogsRepository(session).add_log(
            account_id=None,
            latency_ms=1,
            status="success",
            error_code=None,
            request_id="unpublished-price",
            model=model,
            service_tier=service_tier,
            input_tokens=input_tokens,
            cached_input_tokens=0,
            cache_write_tokens=0,
            output_tokens=1_000,
        )

    response = await async_client.get("/api/request-logs?limit=20")
    assert response.status_code == 200
    row = next(row for row in response.json()["requests"] if row["requestId"] == "unpublished-price")
    assert row["costUsd"] is None
    assert row["costStatus"] == "unknown_pricing"
    assert row["pricingVersion"] == get_pricing_version(row.get("actualModel") or row["model"])
    assert all(value is None for value in row["costBreakdown"].values())

    async with SessionLocal() as session:
        saved = await session.scalar(select(RequestLog).where(RequestLog.request_id == "unpublished-price"))
        assert (
            saved is not None
            and saved.cost_usd is None
            and saved.pricing_version == get_pricing_version(saved.actual_model or saved.model)
        )


@pytest.mark.asyncio
async def test_request_cost_provenance_tracks_catalog_refresh_without_repricing(async_client, db_setup):
    from dataclasses import replace

    from app.core.usage.pricing import get_pricing_for_model, get_pricing_version
    from app.core.usage.pricing_catalog import get_active_prices, install_prices

    original = dict(get_active_prices())
    model = "gpt-5.1"
    resolved = get_pricing_for_model(model)
    assert resolved is not None
    before_price = resolved[1]
    before_version = get_pricing_version(model, before_price)
    try:
        async with SessionLocal() as session:
            repo = RequestLogsRepository(session)
            old = await repo.add_log(
                account_id=None,
                latency_ms=1,
                status="success",
                error_code=None,
                request_id="catalog-before",
                model=model,
                input_tokens=1_000_000,
                output_tokens=0,
                cached_input_tokens=0,
                cache_write_tokens=0,
            )
            old_cost = old.cost_usd
            assert old.pricing_version == before_version
            new_price = replace(before_price, input_per_1m=before_price.input_per_1m * 2)
            install_prices({**original, model: new_price})
            new = await repo.add_log(
                account_id=None,
                latency_ms=1,
                status="success",
                error_code=None,
                request_id="catalog-after",
                model=model,
                input_tokens=1_000_000,
                output_tokens=0,
                cached_input_tokens=0,
                cache_write_tokens=0,
            )
            assert new.pricing_version == get_pricing_version(model, new_price) != before_version
            assert new.cost_usd == pytest.approx(new_price.input_per_1m)
        response = await async_client.get("/api/request-logs?limit=20")
        assert response.status_code == 200
        rows = {row["requestId"]: row for row in response.json()["requests"]}
        assert rows["catalog-before"]["pricingVersion"] == before_version
        assert rows["catalog-before"]["costUsd"] == old_cost
        assert rows["catalog-before"]["costStatus"] == "historical"
        assert rows["catalog-before"]["costBreakdown"]["inputUsd"] is None
        assert rows["catalog-after"]["costStatus"] == "estimated"
    finally:
        install_prices(original)


@pytest.mark.asyncio
async def test_versioned_unknown_cost_waits_for_atomic_backfill_after_catalog_refresh(async_client, db_setup):
    from dataclasses import replace

    from app.core.usage.pricing import ModelPrice, get_pricing_version
    from app.core.usage.pricing_catalog import get_active_prices, install_prices
    from app.modules.request_logs.cost_backfill import backfill_missing_costs

    original = dict(get_active_prices())
    model = "gpt-review-proof"
    before_price = ModelPrice(input_per_1m=1.0, output_per_1m=2.0, cached_input_per_1m=0.1)
    try:
        install_prices({**original, model: before_price})
        async with SessionLocal() as session:
            row = await RequestLogsRepository(session).add_log(
                account_id=None,
                latency_ms=1,
                status="success",
                error_code=None,
                request_id="catalog-unknown-flex",
                model=model,
                service_tier="flex",
                input_tokens=100,
                output_tokens=10,
                cached_input_tokens=0,
                cache_write_tokens=0,
            )
            before_version = row.pricing_version
            assert row.cost_usd is None
            assert before_version == get_pricing_version(model, before_price)
        after_price = replace(
            before_price, flex_input_per_1m=0.5, flex_output_per_1m=1.0, flex_cached_input_per_1m=0.05
        )
        install_prices({**original, model: after_price})
        after_version = get_pricing_version(model, after_price)
        assert after_version != before_version

        response = await async_client.get("/api/request-logs?limit=20")
        assert response.status_code == 200
        row = next(row for row in response.json()["requests"] if row["requestId"] == "catalog-unknown-flex")
        assert row["costUsd"] is None
        assert row["costStatus"] == "unknown_pricing"
        assert row["pricingVersion"] == before_version
        assert all(value is None for value in row["costBreakdown"].values())

        async with SessionLocal() as session:
            assert (await backfill_missing_costs(session)).updated == 1
        response = await async_client.get("/api/request-logs?limit=20")
        assert response.status_code == 200
        row = next(row for row in response.json()["requests"] if row["requestId"] == "catalog-unknown-flex")
        assert row["costUsd"] == pytest.approx(0.00006)
        assert row["costStatus"] == "estimated"
        assert row["pricingVersion"] == after_version
        assert row["costBreakdown"]["totalUsd"] == pytest.approx(0.00006)
    finally:
        install_prices(original)
