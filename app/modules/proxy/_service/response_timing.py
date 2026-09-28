from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.core.types import JsonValue
from app.core.utils.sse import parse_sse_data_json

TERMINAL_EVENT_TYPES = frozenset({"response.completed", "response.failed", "response.incomplete", "error"})
OUTPUT_DELTA_EVENT_TYPES = frozenset(
    {
        "response.output_text.delta",
        "response.refusal.delta",
        "response.function_call_arguments.delta",
        "response.output_tool_call.delta",
        "response.custom_tool_call_input.delta",
    }
)


_MAX_FAST_OUTPUT_CHARACTERS = 64 * 1024

# A complete, conservative flat-object subset of canonical upstream deltas.
# Excluding content keys from metadata rejects duplicate/multiple output fields;
# escaped keys, nested metadata and other unknown shapes use the existing parser.
# Possessive repetitions keep malformed strings from triggering backtracking.
# Bounded number tokens retain the decoder's large-integer limit/error behavior.
_JSON_STRING = r'"[^"\\\x00-\x1f]*+(?:\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})[^"\\\x00-\x1f]*+)*+"'
_JSON_NUMBER = r"-?(?:0|[1-9][0-9]{0,18})(?:\.[0-9]{1,18})?(?:[eE][+-]?[0-9]{1,4})?"
_JSON_SPACE = r"[ \t]*"
_METADATA_KEY = r'"(?:type|sequence_number|item_id|output_index|content_index|call_id|obfuscation|logprobs)"'
_METADATA_VALUE = rf"(?:{_JSON_STRING}|{_JSON_NUMBER}|true|false|null|\[{_JSON_SPACE}\])"
_METADATA_FIELD = rf"{_METADATA_KEY}{_JSON_SPACE}:{_JSON_SPACE}{_METADATA_VALUE}"
_CANONICAL_OUTPUT_PAYLOAD = re.compile(
    rf"\{{{_JSON_SPACE}(?:{_METADATA_FIELD}{_JSON_SPACE},{_JSON_SPACE})*"
    rf'"(?:delta|arguments|input)"{_JSON_SPACE}:{_JSON_SPACE}(?P<output>{_JSON_STRING})'
    rf"(?:{_JSON_SPACE},{_JSON_SPACE}{_METADATA_FIELD})*{_JSON_SPACE}\}}"
)


class OutputTimingState(Protocol):
    started_at: float
    latency_first_output_ms: int | None
    output_delta_count: int
    ended_at: float | None


@dataclass(slots=True)
class ResponseTiming:
    started_at: float
    latency_first_output_ms: int | None = None
    output_delta_count: int = 0
    ended_at: float | None = None


def _nonempty_string(value: JsonValue | None) -> bool:
    return isinstance(value, str) and bool(value)


def _item_has_output(item: JsonValue | None) -> bool:
    if not isinstance(item, dict):
        return False
    item_type = item.get("type")
    if item_type in {"function_call", "custom_tool_call", "apply_patch_call"}:
        return any(_nonempty_string(item.get(key)) for key in ("arguments", "input"))
    if item_type != "message":
        return False
    content = item.get("content")
    if not isinstance(content, list):
        return False
    return any(
        isinstance(part, dict)
        and (
            (part.get("type") == "output_text" and _nonempty_string(part.get("text")))
            or (part.get("type") == "refusal" and _nonempty_string(part.get("refusal")))
        )
        for part in content
    )


def has_non_reasoning_output(
    event_type: str | None, payload: dict[str, JsonValue] | None, *, allow_snapshot: bool
) -> bool:
    """Inspect delivered content, never usage totals or lifecycle metadata."""
    if payload is None:
        return False
    if event_type in OUTPUT_DELTA_EVENT_TYPES:
        return any(_nonempty_string(payload.get(key)) for key in ("delta", "arguments", "input"))
    if event_type == "response.output_item.added":
        item = payload.get("item")
        return (
            isinstance(item, dict)
            and item.get("type") in {"custom_tool_call", "apply_patch_call"}
            and _item_has_output(item)
        )
    if not allow_snapshot:
        return False
    if event_type == "response.output_item.done":
        return _item_has_output(payload.get("item"))
    snapshot_field = {
        "response.output_text.done": "text",
        "response.refusal.done": "refusal",
        "response.function_call_arguments.done": "arguments",
        "response.custom_tool_call_input.done": "input",
    }.get(event_type or "")
    if snapshot_field is not None:
        return _nonempty_string(payload.get(snapshot_field))
    if event_type in TERMINAL_EVENT_TYPES:
        response = payload.get("response")
        output = response.get("output") if isinstance(response, dict) else None
        return isinstance(output, list) and any(_item_has_output(item) for item in output)
    return False


def observe_output_timing(
    state: OutputTimingState,
    event_type: str | None,
    payload: dict[str, JsonValue] | None,
    *,
    observed_at: float,
) -> None:
    # Full snapshots repeat previously streamed content. Use one only when
    # there was no output delta; it remains an insufficient, single-chunk sample.
    if not has_non_reasoning_output(event_type, payload, allow_snapshot=state.output_delta_count == 0):
        return
    _record_output_timing(state, observed_at=observed_at)


def observe_verbatim_output_timing(
    state: OutputTimingState,
    event_type: str,
    event_block: str,
    *,
    observed_at: float,
) -> None:
    """Observe an already-classified canonical frame without decoding common deltas."""
    if event_type not in OUTPUT_DELTA_EVENT_TYPES:
        return
    # The relay classifier has already checked leading event/data lines and LF
    # terminators. Match in-place to avoid copying the potentially large payload.
    payload_start = event_block.find("\n") + len("\ndata: ")
    match = (
        _CANONICAL_OUTPUT_PAYLOAD.fullmatch(event_block, payload_start, len(event_block) - 2)
        if len(event_block) <= _MAX_FAST_OUTPUT_CHARACTERS
        else None
    )
    if match is None:
        observe_output_timing(state, event_type, parse_sse_data_json(event_block), observed_at=observed_at)
    elif match.end("output") - match.start("output") > 2:
        # A validated JSON string is empty only when its encoded span is `""`.
        _record_output_timing(state, observed_at=observed_at)


def _record_output_timing(state: OutputTimingState, *, observed_at: float) -> None:
    if state.latency_first_output_ms is None:
        state.latency_first_output_ms = max(0, int((observed_at - state.started_at) * 1000))
    state.output_delta_count += 1


def finish_response_timing(state: OutputTimingState, *, ended_at: float) -> int:
    """Freeze the final outcome before settlement and cleanup await points."""
    if state.ended_at is None:
        state.ended_at = ended_at
    return max(0, int((state.ended_at - state.started_at) * 1000))
