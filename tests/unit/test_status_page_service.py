from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.modules.status_page.schemas import EmailConfigurationUpdate
from app.modules.status_page.service import MonitorConnection, StatusPageService, StatusPageUnavailable

pytestmark = pytest.mark.unit


def connection(tmp_path: Path):
    token = tmp_path / "token.txt"
    token.write_text("test-service-token-" * 4)
    token.chmod(0o600)
    config = tmp_path / "status-monitor.json"
    config.write_text(json.dumps({"url": "http://127.0.0.1:2467", "token_file": str(token)}))
    config.chmod(0o600)
    return config


@pytest.mark.parametrize(
    "url",
    [
        "https://remote.invalid",
        "http://localhost:2467",
        "http://127.0.0.1.evil.invalid",
        "http://127.0.0.1/path",
        "http://user:pass@127.0.0.1",
    ],
)
def test_connector_rejects_non_literal_loopback_origins(url):
    with pytest.raises(ValidationError):
        MonitorConnection(url=url, token_file=Path("/private/test-token"))


@pytest.mark.asyncio
async def test_unconfigured_connection_is_disabled_without_network(tmp_path):
    result = await StatusPageService(tmp_path / "absent.json").get_settings()
    assert result.available is False


@pytest.mark.asyncio
async def test_private_bridge_serialization_and_redacted_errors(tmp_path, monkeypatch):
    config = connection(tmp_path)
    real_client = httpx.AsyncClient
    captured = []

    def handler(request):
        assert request.url.host == "127.0.0.1"
        assert request.headers["Authorization"].startswith("Bearer test-service-token-")
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200, json={**{k: v for k, v in body.items() if k != "password"}, "password_configured": True}
        )

    monkeypatch.setattr(
        "app.modules.status_page.service.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    service = StatusPageService(config)
    result = await service.update_email(
        EmailConfigurationUpdate(
            enabled=True,
            host="smtp.example.invalid",
            port=465,
            tls="ssl",
            sender="a@example.invalid",
            username="a@example.invalid",
            recipients=["b@example.invalid"],
            password=SecretStr("private-auth-code"),
        )
    )
    assert captured[0]["password"] == "private-auth-code"
    assert "private-auth-code" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_get_settings_parses_sanitized_quota_summary(tmp_path, monkeypatch):
    config = connection(tmp_path)
    real_client = httpx.AsyncClient
    payload = {
        "available": True,
        "email": None,
        "quota": {
            "stale": False,
            "collected_at": "2026-10-19T04:00:00+00:00",
            "routability": "operational",
            "routability_detail": "仍有可路由额度",
            "low_quota_status": "degraded",
            "low_quota_threshold": 20,
            "lowest_remaining_percent": 13,
            "active_accounts": 2,
            "quota_ready": 2,
            "quota_unknown": 0,
            "quota_exhausted": 0,
            "weekly_remaining_percent": 41,
            "weekly_next_reset_at": "2026-10-21T04:00:00+00:00",
        },
        "notices": [],
        "events": [],
    }

    def handler(request):
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        "app.modules.status_page.service.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = await StatusPageService(config).get_settings()
    assert result.quota is not None
    assert result.quota.lowest_remaining_percent == 13
    assert result.quota.quota_ready == 2


@pytest.mark.asyncio
async def test_redirects_do_not_forward_control_credential(tmp_path, monkeypatch):
    real_client = httpx.AsyncClient
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://untrusted.invalid"}, text="secret upstream detail")

    monkeypatch.setattr(
        "app.modules.status_page.service.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    with pytest.raises(StatusPageUnavailable) as exc:
        await StatusPageService(connection(tmp_path)).get_settings()
    assert len(calls) == 1
    assert "secret upstream" not in str(exc.value)
