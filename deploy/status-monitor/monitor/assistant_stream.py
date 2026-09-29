from __future__ import annotations

import json
import re
from dataclasses import dataclass

MAX_STREAM_BYTES = 4 * 1024 * 1024
MAX_EVENT_BYTES = 256 * 1024
MAX_SNAPSHOT_BYTES = 64 * 1024


@dataclass(frozen=True)
class ModelSnapshot:
    text: str


class SSEDecoder:
    """Bounded byte framing; decode UTF-8 only after a complete SSE event."""

    def __init__(self):
        self.buffer = b""
        self.lines: list[bytes] = []
        self.event_bytes = 0
        self.total = 0

    def feed(self, chunk: bytes) -> list[str]:
        self.total += len(chunk)
        if self.total > MAX_STREAM_BYTES:
            raise ValueError("Stream too large")
        self.buffer += chunk
        events = []
        while match := re.search(rb"\r\n|\n|\r(?=.)", self.buffer, re.DOTALL):
            line, self.buffer = self.buffer[: match.start()], self.buffer[match.end() :]
            self.event_bytes += len(line) + 1
            if self.event_bytes > MAX_EVENT_BYTES:
                raise ValueError("Event too large")
            if not line:
                if self.lines:
                    events.append(b"\n".join(self.lines).decode("utf-8"))
                self.lines, self.event_bytes = [], 0
            elif line.startswith(b"data:"):
                data = line[5:]
                self.lines.append(data[1:] if data.startswith(b" ") else data)
        if len(self.buffer) + self.event_bytes > MAX_EVENT_BYTES:
            raise ValueError("Event too large")
        return events


def answer_preview(snapshot: str) -> str:
    """Expose only the answer field, never JSON scaffolding or citation IDs."""
    try:
        value = json.loads(snapshot)
        text = value.get("answer", "") if isinstance(value, dict) else ""
        return text[:6000] if isinstance(text, str) else ""
    except ValueError:
        pass
    match = re.match(r'^\s*\{\s*"answer"\s*:\s*"', snapshot)
    if not match:
        return ""
    remainder = snapshot[match.end() :]
    try:
        text, _ = json.JSONDecoder().raw_decode('"' + remainder)
        return text[:6000] if isinstance(text, str) else ""
    except ValueError:
        # Hold a trailing partial escape until the next full snapshot arrives.
        for trim in range(min(7, len(remainder) + 1)):
            prefix = remainder[: len(remainder) - trim] if trim else remainder
            try:
                return json.loads('"' + prefix + '"')[:6000]
            except ValueError:
                continue
    return ""


class DiffusionState:
    def __init__(self):
        self.text = ""
        self.stopped = False
        self.done = False

    def consume(self, data: str) -> str | None:
        if self.done:
            raise ValueError("Data after stream terminator")
        if data.strip() == "[DONE]":
            if not self.stopped:
                raise ValueError("Missing successful finish reason")
            self.done = True
            return None
        payload = json.loads(data)
        if not isinstance(payload, dict) or "error" in payload:
            raise ValueError("Invalid model event")
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise ValueError("Expected one completion")
        if not choices:  # Usage-only chunks are not text updates.
            return None
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("index", 0) != 0:
            raise ValueError("Invalid choice")
        delta = choice.get("delta")
        if not isinstance(delta, dict) or delta.get("tool_calls") or delta.get("refusal"):
            raise ValueError("Invalid delta")
        content = delta.get("content")
        finish = choice.get("finish_reason")
        if finish not in (None, "stop"):
            raise ValueError("Incomplete model answer")
        updated = None
        if content is not None and not (content == "" and finish is not None):
            if self.stopped or not isinstance(content, str):
                raise ValueError("Invalid snapshot")
            if len(content.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
                raise ValueError("Snapshot too large")
            self.text = content
            updated = answer_preview(content)
        if finish == "stop":
            self.stopped = True
        return updated
