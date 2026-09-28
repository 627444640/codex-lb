from __future__ import annotations

import json
import sys
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.types import JsonValue
from app.core.utils.sse import parse_sse_data_json
from app.modules.proxy._service import response_timing as timing

pytestmark = pytest.mark.unit
EVENT = "response.output_text.delta"


def _block(payload: dict[str, JsonValue], event: str = EVENT) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@pytest.mark.parametrize("event", sorted(timing.OUTPUT_DELTA_EVENT_TYPES))
@pytest.mark.parametrize("field", ["delta", "arguments", "input"])
@pytest.mark.parametrize("content", ["", " ", "hello", "你好안녕", '"quoted"\\path', "\n\t\x00", "\u2028\u2029"])
def test_supported_flat_output_preserves_nonempty_samples_without_decoding(monkeypatch, event, field, content):
    parser = MagicMock(side_effect=AssertionError("common output frame must not decode JSON"))
    monkeypatch.setattr(timing, "parse_sse_data_json", parser)
    state = timing.ResponseTiming(started_at=10.0)
    payload = {
        "type": event,
        "sequence_number": 42,
        "item_id": "msg_example",
        "output_index": 0,
        "content_index": 0,
        field: content,
        "logprobs": [],
        "obfuscation": "x",
    }

    timing.observe_verbatim_output_timing(state, event, _block(payload, event), observed_at=10.25)

    assert state.output_delta_count == int(bool(content))
    assert state.latency_first_output_ms == (250 if content else None)
    assert state.ended_at is None
    parser.assert_not_called()


@pytest.mark.parametrize(
    "encoded",
    [
        '{"delta":"first","delta":""}',
        '{"delta":"","delta":"last"}',
        r'{"\u0064elta":"escaped key"}',
        '{"delta":"","input":"real input"}',
        '{"delta":null,"arguments":"{}"}',
        '{"delta":{"nested":"not content"}}',
        '{"metadata":{"delta":"not a root value"},"delta":""}',
        '{"delta":"real output","metadata":{"extra":true}}',
        '{"delta":"","logprobs":[{"token":"not content"}]}',
        '{"delta":123}',
        '{"delta":false}',
        '{"type":"response.output_text.delta"}',
        '{"delta":"invalid trailing comma",}',
        r'{"delta":"invalid \q escape"}',
        r'{"delta":"invalid \u000g escape"}',
        '{"delta":"","sequence_number":01}',
        '{"delta":"","sequence_number":NaN}',
        '{"delta":""\u000b}',
        '{"delta":"raw\x00control"}',
        '{"delta":"' + "x" * 16_384,
    ],
)
def test_unknown_and_ambiguous_shapes_retain_existing_decoder_semantics(monkeypatch, encoded):
    block = f"event: {EVENT}\ndata: {encoded}\n\n"
    parser = MagicMock(wraps=parse_sse_data_json)
    monkeypatch.setattr(timing, "parse_sse_data_json", parser)
    initial = timing.ResponseTiming(started_at=10.0, latency_first_output_ms=100, output_delta_count=2)
    expected, actual = replace(initial), replace(initial)

    timing.observe_output_timing(expected, EVENT, parse_sse_data_json(block), observed_at=11.0)
    timing.observe_verbatim_output_timing(actual, EVENT, block, observed_at=11.0)

    assert actual == expected
    parser.assert_called_once_with(block)


@pytest.mark.parametrize(
    "event", ["response.reasoning_summary_text.delta", "response.output_text.done", "codex.keepalive"]
)
def test_non_output_fast_frames_do_not_change_timing(monkeypatch, event):
    parser = MagicMock(side_effect=AssertionError("unobserved fast frame must not decode JSON"))
    monkeypatch.setattr(timing, "parse_sse_data_json", parser)
    state = timing.ResponseTiming(started_at=10.0)

    timing.observe_verbatim_output_timing(state, event, _block({"delta": "text"}, event), observed_at=11.0)

    assert state == timing.ResponseTiming(started_at=10.0)
    parser.assert_not_called()


json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text(),
    lambda child: st.lists(child, max_size=3) | st.dictionaries(st.text(max_size=12), child, max_size=3),
    max_leaves=10,
)


@settings(max_examples=300, deadline=None)
@given(
    st.dictionaries(
        st.sampled_from(
            ["type", "delta", "arguments", "input", "item_id", "output_index", "sequence_number", "logprobs", "extra"]
        ),
        json_values,
        max_size=8,
    )
)
def test_canonical_observation_matches_decoder_for_generated_payloads(payload):
    block = _block(payload)
    expected = timing.ResponseTiming(started_at=0.0)
    actual = timing.ResponseTiming(started_at=0.0)

    for observed_at in (0.25, 1.0):
        timing.observe_output_timing(expected, EVENT, parse_sse_data_json(block), observed_at=observed_at)
        timing.observe_verbatim_output_timing(actual, EVENT, block, observed_at=observed_at)

    assert actual == expected


def test_large_frame_uses_decoder_and_preserves_observation(monkeypatch):
    block = _block({"delta": "x" * (65 * 1024)})
    parser = MagicMock(wraps=parse_sse_data_json)
    monkeypatch.setattr(timing, "parse_sse_data_json", parser)
    state = timing.ResponseTiming(started_at=0.0)

    timing.observe_verbatim_output_timing(state, EVENT, block, observed_at=1.0)

    assert state.output_delta_count == 1
    assert state.latency_first_output_ms == 1000
    parser.assert_called_once_with(block)


def test_large_integer_guard_keeps_existing_decoder_failure():
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("interpreter integer-conversion limit is disabled")
    encoded = '{"sequence_number":' + "9" * (limit + 1) + ',"delta":"hello"}'
    block = f"event: {EVENT}\ndata: {encoded}\n\n"
    with pytest.raises(ValueError) as previous:
        parse_sse_data_json(block)
    state = timing.ResponseTiming(started_at=0.0)

    with pytest.raises(type(previous.value)):
        timing.observe_verbatim_output_timing(state, EVENT, block, observed_at=1.0)

    assert state.output_delta_count == 0
    assert state.latency_first_output_ms is None
