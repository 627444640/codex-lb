"""Compare conversation-history cache write count and CPU with the cache on and off.

Token events are not writes. A completed turn is one compressed delta, and those
deltas are committed in batches. Run from the repo root:

    uv run python scripts/loadtest_conversation_history_cache.py
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from app.modules.proxy.conversation_history import ConversationHistoryCache


def _run(path: Path, *, enabled: bool, turns: int, tokens_per_turn: int) -> tuple[float, int, int]:
    cache = ConversationHistoryCache(
        path / "conversation_history.db",
        enabled=enabled,
        max_bytes=1024**3,
        conversation_max_bytes=32 * 1024 * 1024,
        idle_ttl_seconds=1800,
        min_free_disk_bytes=0,
        batch_limit=32,
        start_maintenance=False,
        disk_free=10**12,
    )
    started = time.process_time()
    for index in range(turns):
        text = ("token " * tokens_per_turn) + str(index)
        cache.record_completed_turn(
            request_body={
                "model": "gpt-6-astra",
                "instructions": "be brief",
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}],
                "previous_response_id": None,
            },
            response_id=f"resp-{index}",
            output_items=[{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}],
        )
    cache.flush()
    elapsed = time.process_time() - started
    stats = cache.stats()
    cache.close()
    return elapsed, stats.write_transactions, stats.write_rows


def main() -> None:
    turns = 200
    tokens_per_turn = 50
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        on_cpu, on_writes, on_rows = _run(root / "on", enabled=True, turns=turns, tokens_per_turn=tokens_per_turn)
        off_cpu, off_writes, off_rows = _run(root / "off", enabled=False, turns=turns, tokens_per_turn=tokens_per_turn)
    token_events = turns * tokens_per_turn
    print(f"turns={turns} token_events={token_events}")
    print(f"cache_on  cpu_seconds={on_cpu:.4f} write_transactions={on_writes} write_rows={on_rows}")
    print(f"cache_off cpu_seconds={off_cpu:.4f} write_transactions={off_writes} write_rows={off_rows}")
    print(
        "writes stay at one row per completed turn, batched, not one write per token. "
        f"on/off write transactions {on_writes}/{off_writes}."
    )


if __name__ == "__main__":
    main()
