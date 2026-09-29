from __future__ import annotations

import json
import re
from dataclasses import dataclass
from itertools import islice

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


def _noisy_answer_value(snapshot: str) -> str:
    """The answer is the only long string in the requested schema.

    Denoising may remove a key's quote or colon, changing quote pairing. Try
    bounded, overlapping string starts rather than returning the JSON wrapper.
    """
    best = ""
    decoder = json.JSONDecoder(strict=False)
    for match in islice(re.finditer('"', snapshot), 32):
        try:
            text, _ = decoder.raw_decode(snapshot, match.start())
        except ValueError:
            continue
        if not isinstance(text, str):
            continue
        text = text.strip()
        if (
            len(text) > max(15, len(best))
            and not text.startswith((":", ",", "{", "}", "[", "]"))
            and re.search(r"[^\W\d_]", text)
        ):
            best = text[:6000]
    return best


def answer_preview(snapshot: str, *, diffusing: bool = False) -> str:
    """Expose only the answer field, never JSON scaffolding or citation IDs."""
    try:
        value = json.loads(snapshot)
        text = value.get("answer") if isinstance(value, dict) else None
        if isinstance(text, str):
            return text[:6000]
        if not diffusing:
            return ""
    except ValueError:
        pass
    match = re.match(r'^\s*\{\s*"answer"\s*:\s*"', snapshot)
    if not match and diffusing:
        # Inception denoises the JSON syntax too. The requested first field is
        # the answer string; expose its value only when the delimiter survives.
        match = re.match(r'^\s*\{\s*([^{}:\r\n]{1,48}?)\s*:\s*"', snapshot)
        if match and match.group(1).strip().strip('"') == "source_ids":
            return ""
    if not match:
        return _noisy_answer_value(snapshot) if diffusing else ""
    remainder = snapshot[match.end() :]
    try:
        text, _ = json.JSONDecoder(strict=not diffusing).raw_decode('"' + remainder)
        return text[:6000] if isinstance(text, str) else ""
    except ValueError:
        # Hold a trailing partial escape until the next full snapshot arrives.
        for trim in range(min(7, len(remainder) + 1)):
            prefix = remainder[: len(remainder) - trim] if trim else remainder
            try:
                return json.loads('"' + prefix + '"', strict=not diffusing)[:6000]
            except ValueError:
                continue
    return _noisy_answer_value(snapshot) if diffusing else ""


class DiffusionState:
    def __init__(self):
        self.text = ""
        self.stopped = False
        self.done = False
        self.events = 0
        self.finish_reason: str | None = None

    def consume(self, data: str) -> str | None:
        self.events += 1
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
        if finish is not None:
            self.finish_reason = finish if finish in {"stop", "length", "content_filter", "tool_calls"} else "other"
        if finish not in (None, "stop"):
            raise ValueError("Incomplete model answer")
        updated = None
        if content is not None and not (content == "" and finish is not None):
            if self.stopped or not isinstance(content, str):
                raise ValueError("Invalid snapshot")
            if len(content.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
                raise ValueError("Snapshot too large")
            self.text = content
            metadata = payload.get("diffusion_meta")
            diffusing = finish is None and isinstance(metadata, dict) and metadata.get("diffusion_content") is True
            updated = answer_preview(content, diffusing=diffusing)
        if finish == "stop":
            self.stopped = True
        return updated
