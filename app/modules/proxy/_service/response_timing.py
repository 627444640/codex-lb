from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.types import JsonValue

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
    if state.latency_first_output_ms is None:
        state.latency_first_output_ms = max(0, int((observed_at - state.started_at) * 1000))
    state.output_delta_count += 1


def finish_response_timing(state: OutputTimingState, *, ended_at: float) -> int:
    """Freeze the final outcome before settlement and cleanup await points."""
    if state.ended_at is None:
        state.ended_at = ended_at
    return max(0, int((state.ended_at - state.started_at) * 1000))
