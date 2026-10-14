from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.requests import ClientDisconnect, Request
from starlette.testclient import TestClient

from app.core.handlers import add_exception_handlers
from app.modules.request_logs.repository import RequestLogsRepository


class _Payload(BaseModel):
    model: str


def _app() -> FastAPI:
    app = FastAPI()
    add_exception_handlers(app)

    @app.post("/v1/responses")
    async def responses(_payload: _Payload) -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/widgets")
    async def widgets(_payload: _Payload) -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
def recorded_logs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    recorded: list[dict[str, object]] = []

    @asynccontextmanager
    async def _session() -> AsyncIterator[object]:
        yield object()

    async def _add_log(self: RequestLogsRepository, **kwargs: object) -> object:
        del self
        recorded.append(dict(kwargs))
        return object()

    monkeypatch.setattr("app.db.session.get_background_session", _session)
    monkeypatch.setattr(RequestLogsRepository, "add_log", _add_log)
    return recorded


def test_body_parse_400_is_written_without_the_body(
    monkeypatch: pytest.MonkeyPatch,
    recorded_logs: list[dict[str, object]],
) -> None:
    secret = b'{"model":"gpt-5.6-sol","secret":"BODY_PARSE_SECRET"}'

    async def _disconnect(self: Request) -> bytes:
        del self
        raise ClientDisconnect()

    monkeypatch.setattr(Request, "body", _disconnect)
    response = TestClient(_app()).post(
        "/v1/responses",
        content=secret,
        headers={"content-type": "application/json", "user-agent": "Codex Desktop/1.2"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "There was an error parsing the body"
    assert len(recorded_logs) == 1
    saved = recorded_logs[0]
    assert saved["status"] == "error"
    assert saved["error_code"] == "invalid_request_error"
    assert saved["error_message"] == "There was an error parsing the body"
    assert saved["failure_phase"] == "validation"
    assert saved["failure_detail"] == "ClientDisconnect"
    assert saved["failure_exception_type"] == "ClientDisconnect"
    assert saved["upstream_status_code"] is None
    assert saved["api_key_id"] is None
    assert saved["account_id"] is None
    assert saved["model"] == ""
    assert saved["transport"] == "http"
    assert saved["useragent"] == "Codex Desktop/1.2"
    assert isinstance(saved["request_id"], str) and saved["request_id"]
    assert "BODY_PARSE_SECRET" not in json.dumps(saved)


def test_json_decode_and_dashboard_body_parse_are_not_recorded(
    monkeypatch: pytest.MonkeyPatch,
    recorded_logs: list[dict[str, object]],
) -> None:
    client = TestClient(_app())
    invalid = client.post(
        "/v1/responses",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert invalid.status_code == 400
    assert recorded_logs == []

    async def _disconnect(self: Request) -> bytes:
        del self
        raise ClientDisconnect()

    monkeypatch.setattr(Request, "body", _disconnect)
    dashboard = client.post(
        "/api/widgets",
        content=b'{"model":"x"}',
        headers={"content-type": "application/json"},
    )
    assert dashboard.status_code == 400
    assert recorded_logs == []
