from __future__ import annotations

import json
import tracemalloc
from collections.abc import AsyncIterator

import pytest
import zstandard as zstd
from httpx import ASGITransport, AsyncByteStream, AsyncClient

from app.core.config.settings import get_settings

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("declared_size", [True, False])
@pytest.mark.asyncio
async def test_zstd_ingress_rejects_expansion_without_allocating_full_output(async_client, monkeypatch, declared_size):
    budget = 1024 * 1024
    parameters = zstd.ZstdCompressionParameters.from_level(3, window_log=20, write_content_size=int(declared_size))
    compressed = zstd.ZstdCompressor(compression_params=parameters).compress(b"x" * (8 * budget))
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", str(budget))
    get_settings.cache_clear()

    tracemalloc.start()
    try:
        response = await async_client.put(
            "/api/settings",
            content=compressed,
            headers={"Content-Encoding": "zstd", "Content-Type": "application/json"},
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    # Includes ASGI/HTTP allocations, but must not contain the 8 MiB output.
    assert peak < 4 * budget


@pytest.mark.asyncio
async def test_zstd_ingress_bounds_decoder_window_and_accepts_small_frame(async_client, monkeypatch):
    body = json.dumps({"stickyThreadsEnabled": True}).encode()
    compressed = zstd.ZstdCompressor(write_content_size=False).compress(body)
    assert zstd.get_frame_parameters(compressed).content_size == zstd.CONTENTSIZE_UNKNOWN
    assert compressed[4] == 0  # No size or dictionary ID: byte 5 is the window descriptor.
    large_window = compressed[:5] + bytes([(24 - 10) << 3]) + compressed[6:]
    assert zstd.get_frame_parameters(large_window).window_size == 16 * 1024 * 1024
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", "1024")
    get_settings.cache_clear()

    headers = {"Content-Encoding": "zstd", "Content-Type": "application/json"}
    rejected = await async_client.put("/api/settings", content=large_window, headers=headers)
    assert rejected.status_code == 413
    assert rejected.json()["error"]["code"] == "payload_too_large"

    accepted = await async_client.put("/api/settings", content=compressed, headers=headers)
    assert accepted.status_code == 200
    assert accepted.json()["stickyThreadsEnabled"] is True


class _ChunkedBody(AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


@pytest.mark.parametrize("budget", [2**32, 2**64])
@pytest.mark.parametrize("declared_size", [True, False])
async def test_zstd_small_request_accepts_large_configured_budget(async_client, monkeypatch, budget, declared_size):
    body = json.dumps({"stickyThreadsEnabled": True}).encode()
    compressed = zstd.ZstdCompressor(write_content_size=declared_size).compress(body)
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", str(budget))
    get_settings.cache_clear()
    accepted = await async_client.put(
        "/api/settings", content=compressed, headers={"Content-Encoding": "zstd", "Content-Type": "application/json"}
    )
    assert accepted.status_code == 200
    assert accepted.json()["stickyThreadsEnabled"] is True


@pytest.mark.asyncio
async def test_zstd_request_decompression(async_client, monkeypatch):
    payload = {
        "stickyThreadsEnabled": True,
        "preferEarlierResetAccounts": False,
    }
    body = json.dumps(payload).encode("utf-8")

    compressed = zstd.ZstdCompressor().compress(body)
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", str(max(len(body), len(compressed)) + 8))
    get_settings.cache_clear()

    response = await async_client.put(
        "/api/settings",
        content=compressed,
        headers={"Content-Encoding": "zstd", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stickyThreadsEnabled"] is True
    assert data["preferEarlierResetAccounts"] is False


@pytest.mark.asyncio
async def test_zstd_request_decompression_rejects_large_payload(async_client, monkeypatch):
    payload = {
        "stickyThreadsEnabled": True,
        "preferEarlierResetAccounts": False,
        "padding": "A" * 512,
    }
    body = json.dumps(payload).encode("utf-8")

    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", "128")
    get_settings.cache_clear()

    compressed = zstd.ZstdCompressor().compress(body)
    response = await async_client.put(
        "/api/settings",
        content=compressed,
        headers={"Content-Encoding": "zstd", "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    payload = response.json()
    assert payload["error"]["code"] == "payload_too_large"


@pytest.mark.asyncio
async def test_uncompressed_chunked_typed_body_is_bounded(async_client, monkeypatch):
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", "128")
    get_settings.cache_clear()
    body = json.dumps(
        {
            "stickyThreadsEnabled": True,
            "preferEarlierResetAccounts": False,
            "padding": "A" * 512,
        }
    ).encode("utf-8")

    response = await async_client.put(
        "/api/settings",
        content=_ChunkedBody(body[:64], body[64:]),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "payload_too_large",
        "message": "Request body exceeds the maximum allowed size",
    }


@pytest.mark.asyncio
async def test_proxy_raw_overflow_uses_openai_envelope_before_auth(async_client, monkeypatch):
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", "32")
    get_settings.cache_clear()

    response = await async_client.post(
        "/v1/chat/completions",
        content=b"x" * 33,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"] == {
        "message": "Request body exceeds the maximum allowed size",
        "type": "invalid_request_error",
        "code": "payload_too_large",
    }
    assert response.headers["x-app-version"]
    assert response.headers["x-request-id"]


@pytest.mark.asyncio
async def test_proxy_malformed_compression_uses_openai_envelope(async_client, monkeypatch):
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", "128")
    get_settings.cache_clear()

    response = await async_client.post(
        "/v1/chat/completions",
        content=b"not-zstd",
        headers={"Content-Encoding": "zstd", "Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "message": "Request body is compressed but could not be decompressed",
        "type": "invalid_request_error",
        "code": "invalid_request_error",
    }


@pytest.mark.asyncio
async def test_trailing_slash_responses_route_bounds_chunked_body_without_redirect(async_client, monkeypatch):
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", "8")
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_RESPONSES_BODY_BYTES", "32")
    get_settings.cache_clear()

    response = await async_client.post(
        "/v1/responses/",
        content=_ChunkedBody(b"x" * 16, b"x" * 17),
        headers={"Content-Type": "application/json"},
        follow_redirects=False,
    )

    assert response.status_code == 413
    assert response.headers.get("location") is None
    assert response.json()["error"]["code"] == "payload_too_large"


@pytest.mark.asyncio
async def test_aliased_responses_budget_preserves_real_proxy_authorization(app_instance, monkeypatch):
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_BODY_BYTES", "8")
    monkeypatch.setenv("CODEX_LB_MAX_DECOMPRESSED_RESPONSES_BODY_BYTES", "256")
    get_settings.cache_clear()
    body = json.dumps(
        {
            "model": "gpt-5.1",
            "input": "valid body that is larger than the general ingress budget",
        }
    ).encode("utf-8")
    assert 8 < len(body) <= 256

    async with app_instance.router.lifespan_context(app_instance):
        transport = ASGITransport(app=app_instance, client=("203.0.113.11", 50001))
        async with AsyncClient(transport=transport, base_url="http://lb.example") as remote_client:
            response = await remote_client.post(
                "/backend-api/codex/v1/responses/",
                content=_ChunkedBody(body[:16], body[16:]),
                headers={"Content-Type": "application/json"},
            )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
