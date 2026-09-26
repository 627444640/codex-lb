from __future__ import annotations

from typing import Literal

import pytest
from sqlalchemy import select

import app.modules.proxy.service as proxy_module
from app.core.clients.proxy import CodexControlResponse, ProxyResponseError
from app.core.config.settings import get_settings
from app.core.errors import openai_error
from app.core.openai.models import CompactResponsePayload
from app.db.models import RequestLog
from app.db.session import SessionLocal
from app.dependencies import get_proxy_service_for_app
from tests.integration.test_proxy_files import _import_account

pytestmark = pytest.mark.integration

Operation = Literal["transcribe", "audio", "files-create", "files-finalize", "thread-goal", "control", "warmup"]
_OPERATIONS: tuple[Operation, ...] = (
    "transcribe",
    "audio",
    "files-create",
    "files-finalize",
    "thread-goal",
    "control",
    "warmup",
)


@pytest.fixture(autouse=True)
def _isolate_application_proxy_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    # Uvicorn has its own independent, startup-only proxy trust setting. Keep
    # the socket peer intact so these route tests exercise the application
    # resolver's configured CIDRs; middleware projection has separate tests.
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "")


def _stub_upstreams(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> None:
    async def fresh(self, account, **kwargs):
        return account

    def raise_if_failed() -> None:
        if fail:
            raise ProxyResponseError(400, openai_error("invalid_request_error", "Synthetic upstream rejection"))

    async def file_response(*args, **kwargs):
        raise_if_failed()
        return {"file_id": "file-client-ip", "upload_url": "https://example.invalid/upload", "status": "success"}

    async def json_response(*args, **kwargs):
        raise_if_failed()
        return {"text": "Synthetic transcript", "goal": None}

    async def control_response(*args, **kwargs):
        raise_if_failed()
        return CodexControlResponse(status_code=200, body=b"{}", headers={"content-type": "application/json"})

    async def compact_response(*args, **kwargs):
        raise_if_failed()
        return CompactResponsePayload.model_validate(
            {"object": "response.compact", "id": "compact-client-ip", "usage": {"input_tokens": 1, "output_tokens": 1}}
        )

    monkeypatch.setattr(proxy_module.ProxyService, "_ensure_fresh_with_budget", fresh)
    monkeypatch.setattr(proxy_module, "core_create_file", file_response)
    monkeypatch.setattr(proxy_module, "core_finalize_file", file_response)
    monkeypatch.setattr(proxy_module, "core_transcribe_audio", json_response)
    monkeypatch.setattr(proxy_module, "core_thread_goal_request", json_response)
    monkeypatch.setattr(proxy_module, "core_codex_control_request", control_response)
    monkeypatch.setattr(proxy_module, "core_compact_responses", compact_response)


async def _prepare_client(async_client, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    await _import_account(async_client, "client-ip-account", "client-ip@example.invalid")
    key_response = await async_client.post("/api/api-keys/", json={"name": "client-ip-test"})
    assert key_response.status_code == 200
    settings = get_settings()
    monkeypatch.setattr(settings, "firewall_trust_proxy_headers", True)
    monkeypatch.setattr(settings, "firewall_trusted_proxy_cidrs", ["127.0.0.1/32"])
    return {"Authorization": f"Bearer {key_response.json()['key']}", "X-Forwarded-For": "203.0.113.27"}


async def _invoke(async_client, operation: Operation, headers: dict[str, str]):
    if operation in {"transcribe", "audio"}:
        return await async_client.post(
            "/backend-api/transcribe" if operation == "transcribe" else "/v1/audio/transcriptions",
            headers=headers,
            files={"file": ("synthetic.wav", b"synthetic-audio", "audio/wav")},
            data={"model": "gpt-4o-transcribe"} if operation == "audio" else {},
        )
    if operation == "files-create":
        return await async_client.post(
            "/backend-api/files", headers=headers, json={"file_name": "synthetic.txt", "file_size": 1}
        )
    if operation == "files-finalize":
        return await async_client.post("/backend-api/files/file-client-ip/uploaded", headers=headers)
    if operation == "thread-goal":
        return await async_client.post(
            "/backend-api/codex/thread/goal/get", headers=headers, json={"threadId": "synthetic-thread"}
        )
    if operation == "control":
        return await async_client.post(
            "/backend-api/codex/analytics-events/events", headers=headers, json={"events": []}
        )
    return await async_client.post("/v1/warmup/force", headers=headers)


@pytest.mark.parametrize("operation", _OPERATIONS)
@pytest.mark.parametrize("fail", [False, True], ids=["success", "failure"])
async def test_auxiliary_request_logs_preserve_trusted_client_ip(
    async_client, monkeypatch, operation: Operation, fail: bool
):
    headers = await _prepare_client(async_client, monkeypatch)
    _stub_upstreams(monkeypatch, fail=fail)

    response = await _invoke(async_client, operation, headers)

    assert response.status_code == (400 if fail and operation != "warmup" else 200)
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog))).scalars().one()
        assert row.client_ip == "203.0.113.27"
        assert row.status == ("error" if fail else "success")


@pytest.mark.parametrize(
    ("trust_headers", "trusted_cidrs", "forwarded_for", "expected_ip"),
    [
        (False, [], "198.51.100.99", "127.0.0.1"),
        (True, ["10.0.0.0/8"], "198.51.100.99", "127.0.0.1"),
        (True, ["127.0.0.1/32"], "198.51.100.99, 203.0.113.27", "203.0.113.27"),
        (True, ["127.0.0.1/32"], "not-an-ip", None),
        (True, ["127.0.0.1/32"], None, None),
    ],
    ids=["trust-disabled", "untrusted-peer", "rightmost-untrusted-hop", "malformed-chain", "missing-chain"],
)
async def test_auxiliary_request_ip_obeys_existing_proxy_trust_policy(
    async_client, monkeypatch, trust_headers, trusted_cidrs, forwarded_for, expected_ip
):
    headers = await _prepare_client(async_client, monkeypatch)
    _stub_upstreams(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "firewall_trust_proxy_headers", trust_headers)
    monkeypatch.setattr(settings, "firewall_trusted_proxy_cidrs", trusted_cidrs)
    if forwarded_for is None:
        headers.pop("X-Forwarded-For")
    else:
        headers["X-Forwarded-For"] = forwarded_for

    response = await _invoke(async_client, "files-create", headers)

    assert response.status_code == 200
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog))).scalars().one()
        assert row.client_ip == expected_ip


async def test_service_warmup_without_client_keeps_ip_null(async_client, app_instance, monkeypatch):
    await _import_account(async_client, "background-ip-account", "background-ip@example.invalid")
    _stub_upstreams(monkeypatch)

    service = get_proxy_service_for_app(app_instance)
    result = await service.warmup(mode="force", headers={"X-Forwarded-For": "198.51.100.99"})
    await service.drain_persistence_tasks(timeout_seconds=5)

    assert len(result.submitted) == 1
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog))).scalars().one()
        assert row.client_ip is None
