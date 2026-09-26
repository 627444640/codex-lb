from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import RequestLog, RequestUsageHourlyRollup
from app.db.session import SessionLocal
from app.modules.accounts.usage_time_rollup import run_hourly_fold_pass
from app.modules.request_logs.repository import RequestLogsRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 12)
REQUESTED_AT = NOW - timedelta(hours=3, minutes=30)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "reasoning_tokens", "expected_total", "usage_status"),
    [
        (100, None, 20, 120, "partial"),
        (100, 40, 20, 140, "complete"),
        (None, 40, 20, 40, "partial"),
        (100, None, None, 100, "partial"),
        (None, None, 20, 20, "partial"),
        (None, None, None, None, "missing"),
        (0, 0, None, 0, "complete"),
        (0, None, 0, 0, "partial"),
    ],
)
async def test_known_tokens_match_routes_before_and_after_hourly_fold(
    async_client, db_setup, monkeypatch, input_tokens, output_tokens, reasoning_tokens, expected_total, usage_status
):
    monkeypatch.setattr("app.modules.dashboard.service.utcnow", lambda: NOW)
    async with SessionLocal() as session:
        await RequestLogsRepository(session).add_log(
            account_id=None,
            request_id="token-consistency",
            model="test-known-token-model",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=30 if input_tokens == 100 else None,
            cache_write_tokens=10 if input_tokens == 100 else None,
            latency_ms=None,
            status="success",
            error_code=None,
            requested_at=REQUESTED_AT,
        )

    for folded in (False, True):
        if folded:
            assert await run_hourly_fold_pass(now=NOW) == 1
        logs_response = await async_client.get("/api/request-logs")
        dashboard_response = await async_client.get("/api/dashboard/overview", params={"timeframe": "1d"})
        reports_response = await async_client.get(
            "/api/reports",
            params={"start_date": "2026-09-26", "end_date": "2026-09-26", "timezone": "UTC"},
        )
        assert logs_response.status_code == dashboard_response.status_code == reports_response.status_code == 200
        row = logs_response.json()["requests"][0]
        assert row["tokens"] == expected_total
        assert row["usageStatus"] == usage_status
        assert row["inputTokens"] == input_tokens
        assert row["outputTokens"] == row["outputTokensRaw"] == output_tokens
        assert row["reasoningTokens"] == reasoning_tokens
        if input_tokens == 100:
            assert row["cachedInputTokens"] == 30
            assert row["cacheWriteTokens"] == 10
        dashboard = dashboard_response.json()
        assert dashboard["summary"]["metrics"]["tokens"] == (expected_total or 0)
        assert sum(point["v"] for point in dashboard["trends"]["tokens"]) == (expected_total or 0)
        reports = reports_response.json()
        assert reports["summary"]["totalInputTokens"] + reports["summary"]["totalOutputTokens"] == (expected_total or 0)
        assert sum(day["inputTokens"] + day["outputTokens"] for day in reports["daily"]) == (expected_total or 0)
        async with SessionLocal() as session:
            stored = (await session.execute(select(RequestLog))).scalar_one()
            assert (stored.input_tokens, stored.output_tokens, stored.reasoning_tokens) == (
                input_tokens,
                output_tokens,
                reasoning_tokens,
            )
            if folded:
                hourly = (await session.execute(select(RequestUsageHourlyRollup))).scalar_one()
                assert hourly.output_tokens == (output_tokens or 0)
                assert hourly.output_or_reasoning_tokens == (
                    output_tokens if output_tokens is not None else reasoning_tokens or 0
                )
