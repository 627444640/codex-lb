from __future__ import annotations

import json

import pytest

from app.modules.model_sources.forwarding import SourceStreamUsageParser, SourceUsageHolder

pytestmark = pytest.mark.unit


def _feed(holder: SourceUsageHolder, events: list[dict], *, fragmented: bool = False) -> None:
    parser = SourceStreamUsageParser(holder, response_shape="responses")
    wire = b"".join(("data: " + json.dumps(event, ensure_ascii=False) + "\r\n\r\n").encode() for event in events)
    for chunk in [wire[index : index + 1] for index in range(len(wire))] if fragmented else [wire]:
        parser.feed(chunk)


@pytest.mark.parametrize("outcome", ["completed", "failed", "incomplete"])
@pytest.mark.parametrize("fragmented", [False, True])
def test_source_terminal_carries_outcome_and_usage_across_fragmented_sse(outcome, fragmented):
    holder = SourceUsageHolder()
    _feed(
        holder,
        [
            {
                "type": f"response.{outcome}",
                "response": {
                    "status": outcome,
                    "error": {"code": "test_failure", "message": "测试"},
                    "usage": {"input_tokens": 100, "output_tokens": 20},
                },
            }
        ],
        fragmented=fragmented,
    )
    assert holder.terminal is not None
    assert holder.terminal.outcome == outcome
    assert holder.usage is not None
    assert (holder.usage.input_tokens, holder.usage.output_tokens) == (100, 20)
    assert (holder.responses_stream_failure() is None) is (outcome == "completed")


@pytest.mark.parametrize("status", ["failed", "incomplete", "in_progress", {}, []])
def test_completed_event_with_conflicting_nested_status_is_not_success(status):
    holder = SourceUsageHolder()
    _feed(holder, [{"type": "response.completed", "response": {"status": status}}])
    assert holder.responses_stream_failure() is not None


def test_first_terminal_prevents_later_usage_or_completion_from_overwriting_failure():
    holder = SourceUsageHolder()
    _feed(
        holder,
        [
            {"type": "response.failed", "response": {"usage": {"input_tokens": 10, "output_tokens": 2}}},
            {"type": "response.completed", "response": {"usage": {"input_tokens": 999, "output_tokens": 999}}},
        ],
    )
    assert holder.terminal is not None and holder.terminal.outcome == "failed"
    assert holder.usage is not None and holder.usage.input_tokens == 10


def test_usage_without_a_terminal_cannot_establish_success():
    holder = SourceUsageHolder()
    _feed(holder, [{"type": "response.in_progress", "response": {"usage": {"input_tokens": 10, "output_tokens": 2}}}])
    failure = holder.responses_stream_failure()
    assert failure is not None and failure.error_code == "stream_incomplete"
    assert holder.usage is not None and holder.usage.output_tokens == 2


@pytest.mark.parametrize("invalid", [-1, True, 1.5, "2", 2**31])
def test_invalid_terminal_counters_cannot_reuse_earlier_valid_usage(invalid):
    holder = SourceUsageHolder()
    _feed(
        holder,
        [
            {"type": "response.in_progress", "response": {"usage": {"input_tokens": 10, "output_tokens": 2}}},
            {"type": "response.completed", "response": {"usage": {"input_tokens": invalid, "output_tokens": 2}}},
        ],
    )
    assert holder.terminal is not None and holder.terminal.outcome == "completed"
    assert holder.usage is None


@pytest.mark.parametrize("cached", [None, 0, 2])
def test_null_or_missing_optional_cache_count_remains_compatible(cached):
    holder = SourceUsageHolder()
    _feed(
        holder,
        [
            {
                "type": "response.completed",
                "response": {
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "input_tokens_details": {"cached_tokens": cached},
                    }
                },
            }
        ],
    )
    assert holder.usage is not None
    assert holder.usage.cached_input_tokens == (cached or 0)


def test_chat_stream_does_not_require_a_responses_terminal():
    holder = SourceUsageHolder()
    parser = SourceStreamUsageParser(holder, response_shape="chat")
    parser.feed(b'data: {"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\ndata: [DONE]\n\n')
    assert holder.usage is not None and holder.usage.input_tokens == 10
    assert holder.responses_stream_failure() is None
