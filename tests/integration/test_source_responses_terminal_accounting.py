from __future__ import annotations

import asyncio
import json

import pytest
from aiohttp import web
from sqlalchemy import select

from app.db.models import ApiKeyUsageReservation, RequestLog
from app.db.session import SessionLocal
from app.modules.api_keys.repository import ApiKeysRepository
from app.modules.api_keys.service import ApiKeysService
from tests.integration.test_model_source_routing import (
    _create_model_source,
    _enable_api_key_auth,
)
from tests.integration.test_model_source_routing import (
    source_upstream as source_upstream,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _key_for_source(client, source_id, *, limited):
    await _enable_api_key_auth(client)
    response = await client.post(
        "/api/api-keys/",
        json={
            "name": "source-outcome-key",
            "assignedSourceIds": [source_id],
            "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 2000}] if limited else [],
        },
    )
    assert response.status_code == 200
    key = response.json()
    if limited:
        async with SessionLocal() as session:
            [limit] = await ApiKeysRepository(session).get_limits_by_key(key["id"])
            limit.current_value = 100
            await session.commit()
    return key


def _response(outcome):
    return {
        "id": "synthetic-source-response",
        "status": outcome,
        "output": [],
        "usage": {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 10}},
        "error": {"code": "synthetic_failure", "message": "synthetic upstream failure"}
        if outcome == "failed"
        else None,
        "incomplete_details": {"reason": "max_output_tokens"} if outcome == "incomplete" else None,
    }


@pytest.mark.parametrize("limited", [False, True])
@pytest.mark.parametrize(
    "mode", ["completed", "failed", "incomplete", "error", "missing_terminal", "contradictory", "negative"]
)
async def test_responses_stream_outcome_controls_accounting_and_preserves_events(
    async_client, source_upstream, monkeypatch, limited, mode
):
    model = "source-terminal-model"
    response_payload = _response("failed" if mode == "contradictory" else mode)
    if mode == "negative":
        response_payload["status"] = "completed"
        response_payload["usage"]["input_tokens"] = -10
    event_type = {
        "missing_terminal": "response.in_progress",
        "contradictory": "response.completed",
        "negative": "response.completed",
        "error": "error",
    }.get(mode, f"response.{mode}")
    event = {"type": event_type, "response": response_payload}
    if mode == "error":
        event["error"] = {"code": "synthetic_failure", "message": "synthetic frame failure"}
    wire = ("data: " + json.dumps(event) + "\r\n\r\n").encode()

    async def upstream(request):
        assert request.path == "/v1/responses"
        stream = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await stream.prepare(request)
        for offset in range(0, len(wire), 7):
            await stream.write(wire[offset : offset + 7])
        await stream.write_eof()
        return stream

    source_id = await _create_model_source(
        async_client, name=model, model=model, base_url=await source_upstream(upstream), supports_responses=True
    )
    key = await _key_for_source(async_client, source_id, limited=limited)
    releases = []
    original_release = ApiKeysService.release_usage_reservation

    async def counted_release(self, reservation_id):
        releases.append(reservation_id)
        return await original_release(self, reservation_id)

    monkeypatch.setattr(ApiKeysService, "release_usage_reservation", counted_release)
    response = await async_client.post(
        "/v1/responses",
        headers={"Authorization": f"Bearer {key['key']}"},
        json={"model": model, "input": "synthetic", "stream": True},
    )
    invalid_limited = limited and mode == "negative"
    assert response.status_code == (502 if invalid_limited else 200)
    if invalid_limited:
        assert response.json()["error"]["code"] == "usage_unavailable"
    else:
        frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert frames[0] == event
        if mode == "missing_terminal":
            assert frames[-1]["type"] == "response.failed"
            assert frames[-1]["response"]["error"]["code"] == "stream_incomplete"
        else:
            assert len(frames) == 1

    unsuccessful = mode not in {"completed", "negative"} or invalid_limited
    async with SessionLocal() as session:
        [log] = (await session.scalars(select(RequestLog).where(RequestLog.model == model))).all()
        assert log.status == ("error" if unsuccessful else "success")
        assert (log.input_tokens, log.output_tokens) == ((None, None) if mode == "negative" else (100, 20))
        reservations = (
            await session.scalars(select(ApiKeyUsageReservation).where(ApiKeyUsageReservation.api_key_id == key["id"]))
        ).all()
        if limited:
            [limit] = await ApiKeysRepository(session).get_limits_by_key(key["id"])
            assert limit.current_value == (100 if unsuccessful else 220)
            assert [row.status for row in reservations] == (["released"] if unsuccessful else ["finalized"])
            assert len(releases) == (1 if unsuccessful else 0)
        else:
            assert not reservations
            assert not releases


@pytest.mark.parametrize("limited", [False, True])
@pytest.mark.parametrize("outcome", ["completed", "failed", "incomplete", None])
async def test_responses_json_explicit_terminal_status_matches_stream_policy(
    async_client, source_upstream, limited, outcome
):
    model = "source-json-outcome"
    payload = _response(outcome)
    if outcome is None:
        del payload["status"]

    async def upstream(request):
        return web.json_response(payload)

    source_id = await _create_model_source(
        async_client, name=model, model=model, base_url=await source_upstream(upstream), supports_responses=True
    )
    key = await _key_for_source(async_client, source_id, limited=limited)
    response = await async_client.post(
        "/v1/responses",
        headers={"Authorization": f"Bearer {key['key']}"},
        json={"model": model, "input": "synthetic", "stream": False},
    )
    assert response.status_code == 200
    assert response.json() == payload
    unsuccessful = outcome in {"failed", "incomplete"}
    async with SessionLocal() as session:
        [log] = (await session.scalars(select(RequestLog).where(RequestLog.model == model))).all()
        assert log.status == ("error" if unsuccessful else "success")
        assert (log.input_tokens, log.output_tokens) == (100, 20)
        if limited:
            [limit] = await ApiKeysRepository(session).get_limits_by_key(key["id"])
            assert limit.current_value == (100 if unsuccessful else 220)


@pytest.mark.parametrize("limited", [False, True])
async def test_responses_disconnect_closes_upstream_releases_once_and_logs_known_usage(
    async_client, source_upstream, monkeypatch, limited
):
    model = "source-disconnect-model"
    started = asyncio.Event()
    allow_end = asyncio.Event()
    closed = asyncio.Event()

    async def upstream(request):
        stream = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await stream.prepare(request)
        await stream.write(
            (
                "data: " + json.dumps({"type": "response.in_progress", "response": _response("in_progress")}) + "\n\n"
            ).encode()
        )
        started.set()
        try:
            await allow_end.wait()
        finally:
            closed.set()
        return stream

    source_id = await _create_model_source(
        async_client, name=model, model=model, base_url=await source_upstream(upstream), supports_responses=True
    )
    key = await _key_for_source(async_client, source_id, limited=limited)
    releases = []
    original_release = ApiKeysService.release_usage_reservation

    async def counted_release(self, reservation_id):
        releases.append(reservation_id)
        return await original_release(self, reservation_id)

    monkeypatch.setattr(ApiKeysService, "release_usage_reservation", counted_release)
    task = asyncio.create_task(
        async_client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {key['key']}"},
            json={"model": model, "input": "synthetic", "stream": True},
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        await asyncio.sleep(0.03)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    finally:
        allow_end.set()
        await asyncio.wait_for(closed.wait(), timeout=5)
    async with SessionLocal() as session:
        [log] = (await session.scalars(select(RequestLog).where(RequestLog.model == model))).all()
        assert log.status == "cancelled"
        assert log.error_code == "client_disconnected"
        assert (log.input_tokens, log.output_tokens) == (100, 20)
        if limited:
            [limit] = await ApiKeysRepository(session).get_limits_by_key(key["id"])
            assert limit.current_value == 100
            assert len(releases) == 1
        else:
            assert not releases


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("outcome", ["failed", "incomplete"])
async def test_source_terminal_errors_preserve_wire_but_do_not_persist_credential_echo(
    async_client, source_upstream, streaming, outcome
):
    model = "source-terminal-secret"
    synthetic_credential = f"token-{model}"
    payload = _response(outcome)
    payload["error"] = {"code": synthetic_credential, "message": f"synthetic echo {synthetic_credential}"}
    payload["incomplete_details"] = {"reason": synthetic_credential}

    async def upstream(request):
        if streaming:
            return web.Response(
                body=("data: " + json.dumps({"type": f"response.{outcome}", "response": payload}) + "\n\n").encode(),
                content_type="text/event-stream",
            )
        return web.json_response(payload)

    await _create_model_source(
        async_client, name=model, model=model, base_url=await source_upstream(upstream), supports_responses=True
    )
    response = await async_client.post(
        "/v1/responses", json={"model": model, "input": "synthetic", "stream": streaming}
    )
    assert response.status_code == 200
    assert synthetic_credential in response.text
    async with SessionLocal() as session:
        [log] = (await session.scalars(select(RequestLog).where(RequestLog.model == model))).all()
        assert log.status == "error"
        assert synthetic_credential not in (log.error_code or "")
        assert synthetic_credential not in (log.error_message or "")
        assert log.error_code == f"source_response_{outcome}"


@pytest.mark.parametrize("limited", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
async def test_cancelled_responses_setup_releases_reservation_and_records_disconnect(
    async_client, monkeypatch, limited, streaming
):
    from app.modules.proxy import api as proxy_api

    model = "source-setup-cancelled"
    source_id = await _create_model_source(
        async_client, name=model, model=model, base_url="http://127.0.0.1:9/v1", supports_responses=True
    )
    key = await _key_for_source(async_client, source_id, limited=limited)
    started = asyncio.Event()
    closed = asyncio.Event()

    async def blocked_open(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(proxy_api, "stream_source_responses" if streaming else "forward_source_responses", blocked_open)
    task = asyncio.create_task(
        async_client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {key['key']}"},
            json={"model": model, "input": "synthetic", "stream": streaming},
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert closed.is_set()
    async with SessionLocal() as session:
        [log] = (await session.scalars(select(RequestLog).where(RequestLog.model == model))).all()
        assert log.status == "cancelled"
        assert log.error_code == "client_disconnected"
        reservations = (await session.scalars(select(ApiKeyUsageReservation))).all()
        if limited:
            [limit] = await ApiKeysRepository(session).get_limits_by_key(key["id"])
            assert limit.current_value == 100
            assert [row.status for row in reservations] == ["released"]
        else:
            assert not reservations


@pytest.mark.parametrize("limited", [False, True])
@pytest.mark.parametrize("outcome", ["completed", "failed", "incomplete", "missing_usage"])
@pytest.mark.parametrize("repeat_cancel", [False, True])
async def test_observed_responses_terminal_wins_over_disconnect_and_repeated_cancellation(
    async_client, monkeypatch, limited, outcome, repeat_cancel
):
    from app.modules.model_sources.forwarding import (
        SourceResponsesStream,
        SourceStreamUsageParser,
        SourceUsageHolder,
        _await_cleanup_deferring_cancellation,
    )
    from app.modules.proxy import api as proxy_api

    model = "source-terminal-before-cancel"
    source_id = await _create_model_source(
        async_client, name=model, model=model, base_url="http://127.0.0.1:9/v1", supports_responses=True
    )
    key = await _key_for_source(async_client, source_id, limited=limited)
    payload = _response("completed" if outcome == "missing_usage" else outcome)
    if outcome == "missing_usage":
        payload.pop("usage")
    event = {"type": f"response.{payload['status']}", "response": payload}
    wire = ("data: " + json.dumps(event) + "\n\n").encode()
    suspended = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_allowed = asyncio.Event()
    closed = asyncio.Event()

    async def finish_cleanup():
        cleanup_started.set()
        await cleanup_allowed.wait()
        closed.set()

    async def fake_open(*args, **kwargs):
        holder = SourceUsageHolder()
        parser = SourceStreamUsageParser(holder, response_shape="responses")

        async def body():
            try:
                parser.feed(wire)
                yield wire
                suspended.set()
                await asyncio.Event().wait()
            finally:
                await _await_cleanup_deferring_cancellation(finish_cleanup())

        return SourceResponsesStream(body=body(), usage_holder=holder, upstream_status_code=200)

    releases = []
    finalized = []
    release_original = ApiKeysService.release_usage_reservation
    finalize_original = ApiKeysService.finalize_usage_reservation

    async def counted_release(self, reservation_id):
        releases.append(reservation_id)
        return await release_original(self, reservation_id)

    async def counted_finalize(self, reservation_id, **kwargs):
        finalized.append(reservation_id)
        return await finalize_original(self, reservation_id, **kwargs)

    monkeypatch.setattr(proxy_api, "stream_source_responses", fake_open)
    monkeypatch.setattr(ApiKeysService, "release_usage_reservation", counted_release)
    monkeypatch.setattr(ApiKeysService, "finalize_usage_reservation", counted_finalize)
    task = asyncio.create_task(
        async_client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {key['key']}"},
            json={"model": model, "input": "synthetic", "stream": True},
        )
    )
    try:
        await asyncio.wait_for(suspended.wait(), timeout=5)
        task.cancel()
        await asyncio.wait_for(cleanup_started.wait(), timeout=5)
        if repeat_cancel:
            task.cancel()
            await asyncio.sleep(0)
        cleanup_allowed.set()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=5)
    finally:
        cleanup_allowed.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert closed.is_set()
    unsuccessful = outcome in {"failed", "incomplete"} or (limited and outcome == "missing_usage")
    async with SessionLocal() as session:
        [log] = (await session.scalars(select(RequestLog).where(RequestLog.model == model))).all()
        assert log.status == ("error" if unsuccessful else "success")
        assert (log.input_tokens, log.output_tokens) == ((None, None) if outcome == "missing_usage" else (100, 20))
        if limited:
            [limit] = await ApiKeysRepository(session).get_limits_by_key(key["id"])
            assert limit.current_value == (100 if unsuccessful else 220)
            assert len(finalized) == (0 if unsuccessful else 1)
            assert len(releases) == (1 if unsuccessful else 0)
        else:
            assert not finalized
            assert not releases


@pytest.mark.parametrize("cancel_phase", ["settlement", "log"])
@pytest.mark.parametrize("repeat_cancel", [False, True])
async def test_completed_responses_json_finishes_accounting_before_propagating_cancel(
    async_client, monkeypatch, cancel_phase, repeat_cancel
):
    from app.modules.model_sources.forwarding import SourceResponsesCompletion, SourceUsage
    from app.modules.proxy import api as proxy_api

    model = "source-json-cancelled-after-terminal"
    source_id = await _create_model_source(
        async_client, name=model, model=model, base_url="http://127.0.0.1:9/v1", supports_responses=True
    )
    key = await _key_for_source(async_client, source_id, limited=True)
    reached = asyncio.Event()
    proceed = asyncio.Event()
    finalized = []
    released = []
    original_finalize = ApiKeysService.finalize_usage_reservation
    original_release = ApiKeysService.release_usage_reservation
    original_log = proxy_api._log_source_chat_completion

    async def complete(*args, **kwargs):
        return SourceResponsesCompletion(
            payload=_response("completed"), usage=SourceUsage(100, 20), timings=None, upstream_status_code=200
        )

    async def blocked_finalize(self, reservation_id, **kwargs):
        finalized.append(reservation_id)
        if cancel_phase == "settlement":
            reached.set()
            await proceed.wait()
        return await original_finalize(self, reservation_id, **kwargs)

    async def counted_release(self, reservation_id):
        released.append(reservation_id)
        return await original_release(self, reservation_id)

    async def blocked_log(*args, **kwargs):
        if cancel_phase == "log":
            reached.set()
            await proceed.wait()
        return await original_log(*args, **kwargs)

    monkeypatch.setattr(proxy_api, "forward_source_responses", complete)
    monkeypatch.setattr(ApiKeysService, "finalize_usage_reservation", blocked_finalize)
    monkeypatch.setattr(ApiKeysService, "release_usage_reservation", counted_release)
    monkeypatch.setattr(proxy_api, "_log_source_chat_completion", blocked_log)
    task = asyncio.create_task(
        async_client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {key['key']}"},
            json={"model": model, "input": "synthetic", "stream": False},
        )
    )
    try:
        await asyncio.wait_for(reached.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        if repeat_cancel:
            task.cancel()
            await asyncio.sleep(0)
        assert not task.done()
        proceed.set()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=5)
    finally:
        proceed.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert len(finalized) == 1
    assert not released
    async with SessionLocal() as session:
        [limit] = await ApiKeysRepository(session).get_limits_by_key(key["id"])
        assert limit.current_value == 220
        [reservation] = (await session.scalars(select(ApiKeyUsageReservation))).all()
        assert reservation.status == "finalized"
        [log] = (await session.scalars(select(RequestLog).where(RequestLog.model == model))).all()
        assert log.status == "success"
        assert (log.input_tokens, log.output_tokens) == (100, 20)
