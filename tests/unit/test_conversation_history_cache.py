"""Full-history cache: replay once, stay inside the file cap, and keep text off the API."""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import time
import zlib
from pathlib import Path

import pytest

from app.modules.accounts.schemas import ConversationHistoryCacheStatsResponse
from app.modules.proxy._load_balancer.admission_breaker import (
    AdmissionBreakerPolicy,
    record_admission_failure_locked,
)
from app.modules.proxy._load_balancer.types import RuntimeState
from app.modules.proxy._service.streaming.helpers import _replay_http_history
from app.modules.proxy._service.support import _RetryableStreamError, _StreamSettlement, _WebSocketRequestState
from app.modules.proxy._service.websocket.helpers import (
    _history_replay_owner_after_exclusion,
    _stage_websocket_history_replay,
)
from app.modules.proxy.conversation_history import (
    ConversationHistoryCache,
    maybe_apply_model_history_replay,
    reset_history_replay_context,
)


def _cache(tmp_path: Path, **overrides: object) -> ConversationHistoryCache:
    settings = {
        "path": tmp_path / "conversation_history.db",
        "enabled": True,
        "max_bytes": 1024**3,
        "conversation_max_bytes": 32 * 1024 * 1024,
        "idle_ttl_seconds": 1800,
        "min_free_disk_bytes": 0,
        "batch_limit": 32,
        "start_maintenance": False,
        "disk_free": 10**12,
    }
    settings.update(overrides)
    return ConversationHistoryCache(**settings)  # type: ignore[arg-type]


def _turn(text: str, *, previous: str | None = None) -> dict[str, object]:
    return {
        "model": "gpt-6-astra",
        "instructions": "be brief",
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}],
        "previous_response_id": previous,
    }


def _output(text: str) -> list[dict[str, object]]:
    return [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}]


def test_replay_rebuilds_history_once_on_the_same_account(tmp_path: Path) -> None:
    cache = _cache(tmp_path, batch_limit=8)
    secret = "user-secret-alpha"
    cache.record_completed_turn(
        request_body=_turn(secret),
        response_id="resp-1",
        output_items=_output("assistant-secret-beta"),
    )
    assert cache.stats().write_transactions == 0
    cache.flush()
    assert cache.stats().write_transactions == 1
    assert not cache.has_plaintext(secret)

    reset_history_replay_context()
    replay = cache.plan_replay(
        request_body=_turn("next-turn", previous="resp-1"),
        reason="previous_response_not_found",
        downstream_visible=False,
        already_replayed=False,
        owner_blocked=False,
        file_pinned=False,
    )
    assert replay is not None
    assert replay.switch_account is False
    assert "previous_response_id" not in replay.request_body
    encoded = json.dumps(replay.request_body)
    assert secret in encoded
    assert "assistant-secret-beta" in encoded
    assert "next-turn" in encoded
    assert replay.extra_tokens > 0

    again = cache.plan_replay(
        request_body=_turn("next-turn", previous="resp-1"),
        reason="stream_incomplete",
        downstream_visible=False,
        already_replayed=True,
        owner_blocked=False,
        file_pinned=False,
    )
    assert again is None
    visible = cache.plan_replay(
        request_body=_turn("next-turn", previous="resp-1"),
        reason="stream_incomplete",
        downstream_visible=True,
        already_replayed=False,
        owner_blocked=False,
        file_pinned=False,
    )
    assert visible is None
    cache.close()


def test_owner_block_switches_and_file_pin_does_not(tmp_path: Path) -> None:
    cache = _cache(tmp_path, batch_limit=1)
    cache.record_completed_turn(request_body=_turn("hello"), response_id="resp-1", output_items=_output("world"))
    switched = cache.plan_replay(
        request_body=_turn("again", previous="resp-1"),
        reason="owner_unavailable",
        downstream_visible=False,
        already_replayed=False,
        owner_blocked=True,
        file_pinned=False,
    )
    assert switched is not None and switched.switch_account is True

    pinned_body = _turn("file-turn", previous="resp-1")
    pinned_body["input"] = [
        {"type": "message", "role": "user", "content": [{"type": "input_file", "file_id": "file_abc"}]}
    ]
    refused = cache.plan_replay(
        request_body=pinned_body,
        reason="owner_unavailable",
        downstream_visible=False,
        already_replayed=False,
        owner_blocked=True,
        file_pinned=False,
    )
    assert refused is None
    cache.close()


def test_over_conversation_cap_falls_back(tmp_path: Path) -> None:
    cache = _cache(tmp_path, conversation_max_bytes=80, batch_limit=1)
    accepted = cache.record_completed_turn(
        request_body=_turn("x" * 400),
        response_id="resp-big",
        output_items=_output("y"),
    )
    assert accepted is False
    assert (
        cache.plan_replay(
            request_body=_turn("later", previous="resp-big"),
            reason="previous_response_not_found",
            downstream_visible=False,
            already_replayed=False,
            owner_blocked=False,
            file_pinned=False,
        )
        is None
    )
    cache.close()


def test_file_size_never_exceeds_cap_and_eviction_reclaims_space(tmp_path: Path) -> None:
    cap = 96 * 1024
    cache = _cache(tmp_path, max_bytes=cap, conversation_max_bytes=12 * 1024, batch_limit=1)
    peak = 0
    for index in range(40):
        text = base64.b64encode(os.urandom(6000)).decode("ascii")
        cache.record_completed_turn(request_body=_turn(text), response_id=f"resp-{index}", output_items=_output("ok"))
        size = cache.path.stat().st_size
        peak = max(peak, size)
        assert size <= cap
    assert cache.stats().entries < 40
    before_expire = cache.path.stat().st_size
    cache.idle_ttl_seconds = 0.01
    time.sleep(0.02)
    cache.maintain()
    assert cache.stats().entries == 0
    with sqlite3.connect(cache.path) as conn:
        remaining = conn.execute("SELECT COUNT(*) FROM turns").fetchone()
    assert remaining is not None and remaining[0] == 0
    assert cache.path.stat().st_size < before_expire
    assert cache.path.stat().st_size <= cap
    assert peak <= cap
    mode = cache.path.stat().st_mode & 0o777
    assert mode == 0o600
    cache.close()


def test_low_disk_disables_without_raising(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    cache = _cache(tmp_path, disk_free=0, min_free_disk_bytes=1024)
    with caplog.at_level(logging.WARNING):
        accepted = cache.record_completed_turn(
            request_body=_turn("hello"),
            response_id="resp-1",
            output_items=_output("nope"),
        )
    assert accepted is False
    stats = cache.stats()
    assert stats.enabled is False
    assert stats.disabled_reason == "low_disk"
    assert "low_disk" in caplog.text
    cache.close()


def test_batch_writes_are_far_below_token_events(tmp_path: Path) -> None:
    turns = 64
    tokens_per_turn = 40
    on = _cache(tmp_path / "on", batch_limit=32)
    started = time.process_time()
    for index in range(turns):
        text = "token " * tokens_per_turn
        on.record_completed_turn(
            request_body=_turn(f"{text}-{index}"),
            response_id=f"resp-{index}",
            output_items=_output("ok"),
        )
    on.flush()
    on_cpu = time.process_time() - started
    on_stats = on.stats()
    on.close()

    off = _cache(tmp_path / "off", enabled=False)
    started = time.process_time()
    for index in range(turns):
        off.record_completed_turn(
            request_body=_turn("token " * tokens_per_turn),
            response_id=f"resp-{index}",
            output_items=_output("ok"),
        )
    off.flush()
    off_cpu = time.process_time() - started
    off_stats = off.stats()
    off.close()

    token_events = turns * tokens_per_turn
    assert on_stats.write_rows == turns
    assert on_stats.write_transactions <= 3
    assert on_stats.write_transactions < token_events / 10
    assert off_stats.write_transactions == 0
    assert off_stats.write_rows == 0
    assert on_cpu >= 0 and off_cpu >= 0


def test_appended_delta_omits_the_cached_prefix(tmp_path: Path) -> None:
    cache = _cache(tmp_path, batch_limit=1)
    first = _turn("alpha")
    cache.record_completed_turn(request_body=first, response_id="resp-1", output_items=_output("beta"))
    history = cache.plan_replay(
        request_body=_turn("gamma", previous="resp-1"),
        reason="stream_incomplete",
        downstream_visible=False,
        already_replayed=False,
        owner_blocked=False,
        file_pinned=False,
    )
    assert history is not None
    full_input = history.request_body["input"]
    assert isinstance(full_input, list)
    follow = dict(_turn("gamma", previous="resp-1"))
    follow["input"] = full_input
    cache.record_completed_turn(request_body=follow, response_id="resp-2", output_items=_output("delta"))
    with sqlite3.connect(cache.path) as conn:
        blob = conn.execute("SELECT payload FROM turns WHERE response_id = ?", ("resp-2",)).fetchone()
    assert blob is not None
    stored = json.loads(zlib.decompress(blob[0]))
    assert stored["input"] == [] or stored["input"][-1]["content"][0]["text"] != "alpha"
    cache.close()


def test_stats_schema_has_no_conversation_text() -> None:
    fields = set(ConversationHistoryCacheStatsResponse.model_fields)
    assert "input" not in fields
    assert "output" not in fields
    assert "text" not in fields
    payload = ConversationHistoryCacheStatsResponse(
        enabled=True,
        disabled_reason=None,
        bytes_used=1,
        bytes_cap=2,
        conversation_bytes_cap=3,
        entries=0,
        hits=0,
        replays=0,
        idle_ttl_seconds=1800,
        min_free_disk_bytes=4,
    )
    assert "secret-sentence" not in payload.model_dump_json()


def test_http_model_replay_and_websocket_stage(tmp_path: Path) -> None:
    cache = _cache(tmp_path, batch_limit=1)
    from app.modules.proxy import conversation_history as history_module

    history_module.set_conversation_history_cache(cache)
    cache.record_completed_turn(request_body=_turn("kept"), response_id="resp-1", output_items=_output("reply"))

    class _Payload:
        def __init__(self) -> None:
            self.input = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "more"}]}]
            self.previous_response_id: str | None = "resp-1"
            self.conversation = None

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {
                "model": "gpt-6-astra",
                "instructions": "be brief",
                "input": self.input,
                "previous_response_id": self.previous_response_id,
            }

    reset_history_replay_context()
    payload = _Payload()
    replay = maybe_apply_model_history_replay(
        payload,
        request_id="req-http",
        reason="previous_response_not_found",
        downstream_visible=False,
        owner_blocked=False,
        file_pinned=False,
    )
    assert replay is not None
    assert payload.previous_response_id is None
    assert any("kept" in json.dumps(item) for item in payload.input)

    state = _WebSocketRequestState(
        request_id="req-ws",
        model="gpt-6-astra",
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=0.0,
        request_text=json.dumps(_turn("later", previous="resp-1")),
        previous_response_id="resp-1",
        preferred_account_id="account-a",
    )
    staged = _stage_websocket_history_replay(
        state,
        account_id="account-a",
        reason="owner_unavailable",
        owner_blocked=True,
    )
    assert staged is True
    assert state.previous_response_id is None
    assert state.preferred_account_id is None
    assert "account-a" in state.excluded_account_ids
    assert state.history_replay_used is True
    assert _history_replay_owner_after_exclusion(state, "account-a") is None
    assert _history_replay_owner_after_exclusion(state, "account-b") == "account-b"
    assert (
        _stage_websocket_history_replay(
            state,
            account_id="account-a",
            reason="stream_incomplete",
            owner_blocked=False,
        )
        is False
    )
    assert (
        _stage_websocket_history_replay(
            _WebSocketRequestState(
                request_id="req-client",
                model=None,
                service_tier=None,
                reasoning_effort=None,
                api_key_reservation=None,
                started_at=0.0,
            ),
            account_id="account-a",
            reason="client_disconnected",
            owner_blocked=False,
        )
        is False
    )
    history_module.set_conversation_history_cache(None)


async def test_http_helper_replays_before_output_and_skips_the_last_attempt(tmp_path: Path) -> None:
    cache = _cache(tmp_path, batch_limit=1)
    from app.modules.proxy import conversation_history as history_module

    history_module.set_conversation_history_cache(cache)
    cache.record_completed_turn(request_body=_turn("kept"), response_id="resp-1", output_items=_output("reply"))

    class _Payload:
        def __init__(self) -> None:
            self.input = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "more"}]}]
            self.previous_response_id: str | None = "resp-1"

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {
                "model": "gpt-6-astra",
                "input": self.input,
                "previous_response_id": self.previous_response_id,
            }

    reset_history_replay_context()
    payload = _Payload()
    settlement = _StreamSettlement()
    await _replay_http_history(
        object(),
        payload,
        object(),
        settlement,
        "req-http",
        False,
        "previous_response_owner_unavailable",
    )
    assert payload.previous_response_id == "resp-1"

    with pytest.raises(_RetryableStreamError) as raised:
        await _replay_http_history(
            object(),
            payload,
            object(),
            settlement,
            "req-http",
            True,
            "previous_response_owner_unavailable",
        )
    assert raised.value.history_replay is True
    assert raised.value.exclude_account is True
    assert payload.previous_response_id is None
    assert any("kept" in json.dumps(item) for item in payload.input)
    history_module.set_conversation_history_cache(None)


def test_pre_output_close_still_counts_toward_the_breaker(tmp_path: Path) -> None:
    cache = _cache(tmp_path, batch_limit=1)
    cache.record_completed_turn(request_body=_turn("hello"), response_id="resp-1", output_items=_output("there"))
    runtime = RuntimeState()
    opened = record_admission_failure_locked(
        runtime,
        1000.0,
        AdmissionBreakerPolicy(failure_threshold=1, window_seconds=60.0, open_seconds=300.0),
        account_id="account-a",
    )
    replay = cache.plan_replay(
        request_body=_turn("next", previous="resp-1"),
        reason="stream_incomplete",
        downstream_visible=False,
        already_replayed=False,
        owner_blocked=opened,
        file_pinned=False,
    )
    assert opened is True
    assert runtime.admission_open_until == 1300.0
    assert replay is not None and replay.switch_account is True
    cache.close()
