"""Compare the old decoded observation with the conservative canonical fast path.

Run with: python -m scripts.benchmark_stream_output_observation
This synthetic microbenchmark does not measure request throughput or model speed.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import timeit
from dataclasses import asdict, dataclass

from app.core.types import JsonValue
from app.core.utils.sse import parse_sse_data_json
from app.modules.proxy._service.response_timing import (
    ResponseTiming,
    observe_output_timing,
    observe_verbatim_output_timing,
)


@dataclass(frozen=True)
class ObservationResult:
    case: str
    frame_bytes: int
    parsed_median_us: float
    fast_median_us: float
    change_percent: float


def benchmark_case(name: str, payload: dict[str, JsonValue], *, iterations: int, repeats: int) -> ObservationResult:
    event_type = "response.output_text.delta"
    block = f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    parsed_state, fast_state = ResponseTiming(started_at=0), ResponseTiming(started_at=0)

    def decoded() -> None:
        observe_output_timing(parsed_state, event_type, parse_sse_data_json(block), observed_at=1.0)

    def fast() -> None:
        observe_verbatim_output_timing(fast_state, event_type, block, observed_at=1.0)

    for _ in range(200):
        decoded()
        fast()
    assert parsed_state == fast_state
    timers = (timeit.Timer(decoded), timeit.Timer(fast))
    samples: tuple[list[float], list[float]] = ([], [])
    for repeat in range(repeats):
        for index in (0, 1) if repeat % 2 == 0 else (1, 0):
            samples[index].append(timers[index].timeit(number=iterations) * 1_000_000 / iterations)
    assert parsed_state == fast_state
    old, new = (statistics.median(sample) for sample in samples)
    return ObservationResult(name, len(block.encode()), round(old, 4), round(new, 4), round((new / old - 1) * 100, 2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.iterations <= 0 or args.repeats <= 0:
        parser.error("iterations and repeats must be positive")
    metadata: dict[str, JsonValue] = {
        "type": "response.output_text.delta",
        "sequence_number": 42,
        "item_id": "msg_synthetic",
        "output_index": 0,
        "content_index": 0,
    }
    cases: list[tuple[str, dict[str, JsonValue]]] = [
        ("short_text", metadata | {"delta": "hello", "logprobs": [], "obfuscation": "x"}),
        ("empty_text", metadata | {"delta": ""}),
        ("unicode_text", metadata | {"delta": "你好안녕하세요"}),
        ("escaped_text", metadata | {"delta": '\n"quoted"\\path'}),
        ("tool_arguments", metadata | {"arguments": '{"command":"pwd"}'}),
        ("large_1k_text", metadata | {"delta": "x" * 1024}),
        ("large_16k_text", metadata | {"delta": "x" * 16_384}),
        ("fallback_nested_metadata", metadata | {"delta": "hello", "extra": {"nested": True}}),
        ("fallback_nonstring_delta", metadata | {"delta": None}),
    ]
    results = [
        asdict(benchmark_case(name, payload, iterations=args.iterations, repeats=args.repeats))
        for name, payload in cases
    ]
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": f"{platform.system()} {platform.machine()}",
                "iterations": args.iterations,
                "repeats": args.repeats,
                "scope": "synthetic output observation only; negative change_percent means less time",
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
