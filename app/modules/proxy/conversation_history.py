"""In-flight conversation history for one transparent full-history replay.

The cache lives in its own SQLite file. Memory keeps an index (keys, sizes,
response ids, last access) and a short batch of already-compressed deltas.
Conversation text is loaded from disk only while a replay body is built.

A turn is stored once, when it completes. Token deltas are not written.
Over the per-conversation cap, that conversation is dropped and later
requests keep the existing fail-closed behavior. Over the file cap, the
least-recently-used conversations are deleted and the free pages are
returned with incremental vacuum. Low free disk disables the cache.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import threading
import time
import zlib
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from app.core.openai.requests import extract_input_file_ids
from app.core.types import JsonValue

logger = logging.getLogger(__name__)

HistoryReplayReason = Literal[
    "previous_response_not_found",
    "stream_incomplete",
    "owner_unavailable",
    "admission_failure",
]


class _MutableReplayPayload(Protocol):
    input: JsonValue
    previous_response_id: str | None
    conversation: str | None


_BATCH_LIMIT = 32
_MAINTENANCE_INTERVAL_SECONDS = 30.0
_PAGE_BYTES = 4096
_TOKEN_CHARS = 4
_STORE_DB_NAME = "store.db"
_CACHE_DB_NAME = "conversation_history.db"

_replay_mark: ContextVar[HistoryReplayMark | None] = ContextVar("history_replay_mark", default=None)
_replayed_request_ids: ContextVar[frozenset[str]] = ContextVar("history_replayed_request_ids", default=frozenset())


@dataclass(frozen=True, slots=True)
class HistoryReplayMark:
    reason: str
    extra_tokens: int


@dataclass(frozen=True, slots=True)
class HistoryReplay:
    """One pre-output resend. ``switch_account`` is set only when the owner cannot take it."""

    request_body: dict[str, JsonValue]
    reason: HistoryReplayReason
    extra_tokens: int
    switch_account: bool


@dataclass(frozen=True, slots=True)
class HistoryCacheStats:
    enabled: bool
    disabled_reason: str | None
    bytes_used: int
    bytes_cap: int
    conversation_bytes_cap: int
    entries: int
    hits: int
    replays: int
    idle_ttl_seconds: int
    min_free_disk_bytes: int
    write_transactions: int
    write_rows: int


@dataclass(slots=True)
class _ConversationMeta:
    stored_bytes: int
    last_access: float
    turn_count: int
    response_ids: list[str]


@dataclass(slots=True)
class _PendingTurn:
    conversation_key: str
    seq: int
    response_id: str
    previous_response_id: str | None
    payload: bytes
    raw_bytes: int
    stored_bytes: int
    response_ids: list[str]


def note_history_replay(reason: str, extra_tokens: int, request_id: str | None = None) -> None:
    """Record the first history replay on this request for the request log."""

    from app.modules.proxy._load_balancer.admission_breaker import mark_transparent_retry

    mark_transparent_retry(request_id)
    if _replay_mark.get() is None:
        _replay_mark.set(HistoryReplayMark(reason=reason, extra_tokens=extra_tokens))


def current_history_replay() -> HistoryReplayMark | None:
    return _replay_mark.get()


def request_history_replayed(request_id: str | None) -> bool:
    if not request_id:
        return False
    return request_id in _replayed_request_ids.get()


def mark_request_history_replayed(request_id: str | None) -> None:
    if not request_id:
        return
    current = _replayed_request_ids.get()
    if request_id in current:
        return
    _replayed_request_ids.set(frozenset((*current, request_id)))


def reset_history_replay_context() -> None:
    from app.modules.proxy._load_balancer.admission_breaker import reset_admission_request_context

    _replay_mark.set(None)
    _replayed_request_ids.set(frozenset())
    reset_admission_request_context()


def _estimate_tokens(items: list[JsonValue]) -> int:
    if not items:
        return 0
    encoded = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return len(encoded) // _TOKEN_CHARS


def _items_equal(left: JsonValue, right: JsonValue) -> bool:
    return json.dumps(left, sort_keys=True, ensure_ascii=False) == json.dumps(right, sort_keys=True, ensure_ascii=False)


def _as_item_list(value: object) -> list[JsonValue] | None:
    if not isinstance(value, list):
        return None
    return value


class ConversationHistoryCache:
    """Append-only compressed turn store with an in-memory index."""

    def __init__(
        self,
        path: Path,
        *,
        enabled: bool = True,
        max_bytes: int = 1024**3,
        conversation_max_bytes: int = 32 * 1024 * 1024,
        idle_ttl_seconds: float = 1800.0,
        min_free_disk_bytes: int = 512 * 1024 * 1024,
        batch_limit: int = _BATCH_LIMIT,
        start_maintenance: bool = False,
        disk_free: int | None = None,
    ) -> None:
        if path.name == _STORE_DB_NAME:
            raise ValueError("conversation history cache must not use store.db")
        self.path = path
        self.max_bytes = max(1, int(max_bytes))
        self.conversation_max_bytes = max(1, min(int(conversation_max_bytes), self.max_bytes))
        self.idle_ttl_seconds = max(1.0, float(idle_ttl_seconds))
        self.min_free_disk_bytes = max(0, int(min_free_disk_bytes))
        self._batch_limit = max(1, int(batch_limit))
        self._settings_enabled = bool(enabled)
        self._disabled_reason: str | None = None if enabled else "disabled"
        self._disk_free_override = disk_free
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._metas: dict[str, _ConversationMeta] = {}
        self._response_index: dict[str, str] = {}
        self._order: list[str] = []
        self._pending: list[_PendingTurn] = []
        self._next_seq: dict[str, int] = {}
        self._hits = 0
        self._replays = 0
        self._write_transactions = 0
        self._write_rows = 0
        self._stop = threading.Event()
        self._maintenance: threading.Thread | None = None
        if self._settings_enabled:
            try:
                self._open()
            except OSError:
                logger.warning("Conversation history cache failed to open", exc_info=True)
                self._disabled_reason = "disk_check_failed"
                self._conn = None
        if start_maintenance and self._settings_enabled and self._conn is not None:
            self._maintenance = threading.Thread(
                target=self._maintenance_loop,
                name="conversation-history-cache",
                daemon=True,
            )
            self._maintenance.start()

    def close(self) -> None:
        self._stop.set()
        thread = self._maintenance
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        with self._lock:
            self._flush_locked()
            conn = self._conn
            self._conn = None
        if conn is not None:
            conn.close()

    def record_completed_turn(
        self,
        *,
        request_body: dict[str, JsonValue],
        response_id: str,
        output_items: list[JsonValue],
        conversation_id: str | None = None,
    ) -> bool:
        """Queue one completed turn. Returns whether the turn was accepted into the batch."""

        response = response_id.strip()
        if not response:
            return False
        previous = _optional_str(request_body.get("previous_response_id"))
        incoming = _as_item_list(request_body.get("input"))
        if incoming is None:
            return False
        with self._lock:
            if not self._runtime_enabled_locked():
                return False
            if response in self._response_index or any(item.response_id == response for item in self._pending):
                return False
            if previous and any(item.response_id == previous for item in self._pending):
                self._flush_locked()
            key = self._conversation_key_locked(previous, response, conversation_id)
            if key is None:
                return False
            history = self._history_items_locked(previous) if previous else []
            previous_known = previous is None or previous in self._response_index
            if previous and not previous_known:
                return False
            delta = _suffix_delta(history, incoming)
            blob_obj = {"input": delta, "output": output_items}
            raw = json.dumps(blob_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            compressed = zlib.compress(raw, level=6)
            stored = len(compressed)
            meta = self._metas.get(key)
            already = 0 if meta is None else meta.stored_bytes
            pending_same = sum(item.stored_bytes for item in self._pending if item.conversation_key == key)
            if already + pending_same + stored > self.conversation_max_bytes:
                self._drop_conversation_locked(key)
                self._flush_locked()
                return False
            seq = self._next_seq.get(key, 0) + 1
            self._next_seq[key] = seq
            carried = [] if meta is None else list(meta.response_ids)
            for item in self._pending:
                if item.conversation_key == key:
                    carried = list(item.response_ids)
            carried.append(response)
            self._pending.append(
                _PendingTurn(
                    conversation_key=key,
                    seq=seq,
                    response_id=response,
                    previous_response_id=previous,
                    payload=compressed,
                    raw_bytes=len(raw),
                    stored_bytes=stored,
                    response_ids=carried,
                )
            )
            if len(self._pending) >= self._batch_limit or self._pending_would_exceed_cap_locked():
                self._flush_locked()
            return True

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def maintain(self) -> None:
        with self._lock:
            self._expire_idle_locked(time.time())
            self._flush_locked()
            self._vacuum_locked()
            self._enforce_file_cap_locked()

    def holds_replayable_history(self, previous_response_id: str | None) -> bool:
        """True when a complete cached chain can rebuild this anchor.

        This does not count a hit or a replay. Callers that only need the
        operator diagnostic use it so a cache miss stays distinguishable from
        a chain that was present but not resent.
        """

        if not previous_response_id:
            return False
        with self._lock:
            if not self._runtime_enabled_locked():
                return False
            self._flush_locked()
            return bool(self._history_items_locked(previous_response_id))

    def plan_replay(
        self,
        *,
        request_body: dict[str, JsonValue],
        reason: HistoryReplayReason,
        downstream_visible: bool,
        already_replayed: bool,
        owner_blocked: bool,
        file_pinned: bool,
        request_id: str | None = None,
    ) -> HistoryReplay | None:
        from app.modules.proxy._load_balancer.admission_breaker import transparent_retry_used

        if downstream_visible or already_replayed or transparent_retry_used(request_id):
            return None
        previous = _optional_str(request_body.get("previous_response_id"))
        current = _as_item_list(request_body.get("input"))
        if previous is None or current is None:
            return None
        with self._lock:
            if not self._runtime_enabled_locked():
                return None
            self._flush_locked()
            history = self._history_items_locked(previous)
            if not history:
                return None
            self._hits += 1
            self._touch_locked(self._response_index.get(previous))
            full = current if _starts_with(current, history) else [*history, *current]
            extra = max(0, _estimate_tokens(full) - _estimate_tokens(current))
            body = dict(request_body)
            body["input"] = full
            body.pop("previous_response_id", None)
            switch = owner_blocked or reason in {"owner_unavailable", "admission_failure"}
            if switch and (file_pinned or extract_input_file_ids(full)):
                return None
            if switch and _optional_str(body.get("conversation")):
                body["conversation"] = None
            self._replays += 1
            replay = HistoryReplay(request_body=body, reason=reason, extra_tokens=extra, switch_account=switch)
        logger.info(
            "Conversation history replay reason=%s extra_tokens=%s switch_account=%s",
            reason,
            extra,
            str(switch).lower(),
        )
        note_history_replay(reason, extra, request_id=request_id)
        return replay

    def stats(self) -> HistoryCacheStats:
        with self._lock:
            self._refresh_disk_locked()
            enabled = self._runtime_enabled_locked()
            return HistoryCacheStats(
                enabled=enabled,
                disabled_reason=self._disabled_reason,
                bytes_used=self._on_disk_bytes(),
                bytes_cap=self.max_bytes,
                conversation_bytes_cap=self.conversation_max_bytes,
                entries=len(self._metas),
                hits=self._hits,
                replays=self._replays,
                idle_ttl_seconds=int(self.idle_ttl_seconds),
                min_free_disk_bytes=self.min_free_disk_bytes,
                write_transactions=self._write_transactions,
                write_rows=self._write_rows,
            )

    def turn_count(self, conversation_key: str) -> int:
        with self._lock:
            meta = self._metas.get(conversation_key)
            return 0 if meta is None else meta.turn_count

    def has_plaintext(self, needle: str) -> bool:
        """True when ``needle`` is retained in the memory index or the pending batch."""

        with self._lock:
            for pending in self._pending:
                if needle in pending.conversation_key or needle in pending.response_id:
                    return True
            for key, meta in self._metas.items():
                if needle in key or any(needle in response_id for response_id in meta.response_ids):
                    return True
            for response_id in self._response_index:
                if needle in response_id:
                    return True
        return False

    def _runtime_enabled_locked(self) -> bool:
        self._refresh_disk_locked()
        return self._settings_enabled and self._disabled_reason is None

    def _refresh_disk_locked(self) -> None:
        if not self._settings_enabled:
            self._disabled_reason = "disabled"
            return
        free = self._free_disk_bytes()
        if free is None:
            self._set_disabled_locked("disk_check_failed")
            return
        if free < self.min_free_disk_bytes:
            self._set_disabled_locked("low_disk")
            return
        if self._disabled_reason in {"low_disk", "disk_check_failed"}:
            self._disabled_reason = None
            logger.warning("Conversation history cache re-enabled reason=disk_recovered")

    def _set_disabled_locked(self, reason: str) -> None:
        if self._disabled_reason == reason:
            return
        self._disabled_reason = reason
        self._pending.clear()
        logger.warning("Conversation history cache disabled reason=%s", reason)

    def _free_disk_bytes(self) -> int | None:
        if self._disk_free_override is not None:
            return self._disk_free_override
        try:
            parent = self.path.parent
            parent.mkdir(parents=True, exist_ok=True)
            return shutil.disk_usage(parent).free
        except OSError:
            logger.warning("Conversation history cache disk check failed", exc_info=True)
            return None

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
        self._chmod()
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        conn.execute(f"PRAGMA page_size={_PAGE_BYTES}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA secure_delete=ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                conversation_key TEXT NOT NULL,
                seq INTEGER NOT NULL,
                response_id TEXT NOT NULL,
                previous_response_id TEXT,
                payload BLOB NOT NULL,
                raw_bytes INTEGER NOT NULL,
                stored_bytes INTEGER NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (conversation_key, seq)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_response_id ON turns(response_id)")
        conn.commit()
        self._conn = conn
        self._load_index()
        os.chmod(self.path, 0o600)

    def _load_index(self) -> None:
        conn = self._conn
        if conn is None:
            return
        rows = conn.execute(
            """
            SELECT conversation_key, seq, response_id, stored_bytes, updated_at
            FROM turns
            ORDER BY conversation_key, seq
            """
        ).fetchall()
        for key, seq, response_id, stored_bytes, updated_at in rows:
            meta = self._metas.get(key)
            if meta is None:
                meta = _ConversationMeta(
                    stored_bytes=0,
                    last_access=float(updated_at),
                    turn_count=0,
                    response_ids=[],
                )
                self._metas[key] = meta
                self._order.append(key)
            meta.stored_bytes += int(stored_bytes)
            meta.turn_count += 1
            meta.last_access = max(meta.last_access, float(updated_at))
            meta.response_ids.append(str(response_id))
            self._response_index[str(response_id)] = key
            self._next_seq[key] = max(self._next_seq.get(key, 0), int(seq))

    def _conversation_key_locked(
        self,
        previous: str | None,
        response_id: str,
        conversation_id: str | None,
    ) -> str | None:
        if previous:
            for item in reversed(self._pending):
                if item.response_id == previous:
                    return item.conversation_key
            existing = self._response_index.get(previous)
            if existing is None:
                return None
            return existing
        named = (conversation_id or "").strip()
        if named:
            return named
        return response_id

    def _history_items_locked(self, response_id: str | None) -> list[JsonValue]:
        if not response_id:
            return []
        chain = self._turn_chain_locked(response_id)
        if chain is None:
            return []
        items: list[JsonValue] = []
        for _key, _response_id, payload in chain:
            turn_input = payload.get("input")
            turn_output = payload.get("output")
            if isinstance(turn_input, list):
                items.extend(turn_input)
            if isinstance(turn_output, list):
                items.extend(turn_output)
        return items

    def _turn_chain_locked(self, response_id: str) -> list[tuple[str, str, dict[str, JsonValue]]] | None:
        conn = self._conn
        if conn is None:
            return None
        chain: list[tuple[str, str, dict[str, JsonValue]]] = []
        seen: set[str] = set()
        current: str | None = response_id
        while current:
            if current in seen:
                return None
            seen.add(current)
            row = conn.execute(
                """
                SELECT conversation_key, response_id, previous_response_id, payload
                FROM turns
                WHERE response_id = ?
                ORDER BY seq DESC
                LIMIT 1
                """,
                (current,),
            ).fetchone()
            if row is None:
                return None
            key, found_id, previous, blob = row
            try:
                decoded = json.loads(zlib.decompress(blob))
            except (zlib.error, json.JSONDecodeError, TypeError):
                return None
            if not isinstance(decoded, dict):
                return None
            chain.append((str(key), str(found_id), decoded))
            current = previous if isinstance(previous, str) and previous else None
        chain.reverse()
        root_previous = chain[0][2]
        del root_previous
        root_row = conn.execute(
            "SELECT previous_response_id FROM turns WHERE response_id = ? ORDER BY seq DESC LIMIT 1",
            (chain[0][1],),
        ).fetchone()
        if root_row is None or root_row[0] not in (None, ""):
            return None
        return chain

    def _pending_would_exceed_cap_locked(self) -> bool:
        incoming = sum(item.stored_bytes for item in self._pending)
        return self._projected_bytes(incoming, len(self._pending)) > self.max_bytes

    def _projected_bytes(self, payload_bytes: int, rows: int) -> int:
        payload_pages = (payload_bytes + _PAGE_BYTES - 1) // _PAGE_BYTES
        return self._on_disk_bytes() + (payload_pages + rows) * _PAGE_BYTES

    def _flush_locked(self) -> None:
        if not self._pending:
            self._enforce_file_cap_locked()
            return
        if not self._runtime_enabled_locked():
            self._pending.clear()
            return
        conn = self._conn
        if conn is None:
            self._pending.clear()
            return
        pending = list(self._pending)
        self._pending.clear()
        grouped: dict[str, list[_PendingTurn]] = {}
        for item in pending:
            grouped.setdefault(item.conversation_key, []).append(item)
        accepted: list[_PendingTurn] = []
        for key, items in grouped.items():
            meta = self._metas.get(key)
            already = 0 if meta is None else meta.stored_bytes
            total = already + sum(item.stored_bytes for item in items)
            if total > self.conversation_max_bytes:
                self._drop_conversation_locked(key)
                continue
            accepted.extend(items)
        if not accepted:
            self._enforce_file_cap_locked()
            return
        incoming = sum(item.stored_bytes for item in accepted)
        self._make_room_locked(
            incoming,
            len(accepted),
            protected={item.conversation_key for item in accepted},
        )
        if self._projected_bytes(incoming, len(accepted)) > self.max_bytes:
            return
        now = time.time()
        conn.executemany(
            """
            INSERT INTO turns (
                conversation_key, seq, response_id, previous_response_id,
                payload, raw_bytes, stored_bytes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.conversation_key,
                    item.seq,
                    item.response_id,
                    item.previous_response_id,
                    item.payload,
                    item.raw_bytes,
                    item.stored_bytes,
                    now,
                )
                for item in accepted
            ],
        )
        conn.commit()
        self._checkpoint_locked()
        self._write_transactions += 1
        self._write_rows += len(accepted)
        for item in accepted:
            meta = self._metas.get(item.conversation_key)
            if meta is None:
                meta = _ConversationMeta(stored_bytes=0, last_access=now, turn_count=0, response_ids=[])
                self._metas[item.conversation_key] = meta
                self._order.append(item.conversation_key)
            meta.stored_bytes += item.stored_bytes
            meta.turn_count += 1
            meta.last_access = now
            meta.response_ids = list(item.response_ids)
            self._response_index[item.response_id] = item.conversation_key
            self._touch_order(item.conversation_key)
        self._enforce_file_cap_locked()
        self._chmod()

    def _make_room_locked(self, incoming: int, rows: int, *, protected: set[str]) -> None:
        while self._order and self._projected_bytes(incoming, rows) > self.max_bytes:
            victim = next((key for key in self._order if key not in protected), None)
            if victim is None:
                return
            self._drop_conversation_locked(victim)
            self._vacuum_locked()

    def _enforce_file_cap_locked(self) -> None:
        while self._on_disk_bytes() > self.max_bytes and self._order:
            self._drop_conversation_locked(self._order[0])
            self._vacuum_locked()

    def _expire_idle_locked(self, now: float) -> None:
        stale = [key for key, meta in self._metas.items() if now - meta.last_access >= self.idle_ttl_seconds]
        if not stale:
            return
        for key in stale:
            self._drop_conversation_locked(key)
        self._vacuum_locked()

    def _drop_conversation_locked(self, key: str) -> None:
        conn = self._conn
        meta = self._metas.pop(key, None)
        if key in self._order:
            self._order.remove(key)
        self._next_seq.pop(key, None)
        self._pending = [item for item in self._pending if item.conversation_key != key]
        if meta is not None:
            for response_id in meta.response_ids:
                if self._response_index.get(response_id) == key:
                    del self._response_index[response_id]
        if conn is None:
            return
        conn.execute("DELETE FROM turns WHERE conversation_key = ?", (key,))
        conn.commit()
        self._checkpoint_locked()
        self._write_transactions += 1

    def _vacuum_locked(self) -> None:
        conn = self._conn
        if conn is None:
            return
        try:
            conn.execute("PRAGMA incremental_vacuum")
            conn.commit()
            self._checkpoint_locked()
        except sqlite3.DatabaseError:
            logger.warning("Conversation history incremental vacuum failed", exc_info=True)

    def _touch_locked(self, key: str | None) -> None:
        if key is None:
            return
        meta = self._metas.get(key)
        if meta is None:
            return
        meta.last_access = time.time()
        self._touch_order(key)

    def _touch_order(self, key: str) -> None:
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)

    def _on_disk_bytes(self) -> int:
        total = 0
        for candidate in (
            self.path,
            Path(str(self.path) + "-journal"),
            Path(str(self.path) + "-wal"),
            Path(str(self.path) + "-shm"),
        ):
            if candidate.exists():
                total += candidate.stat().st_size
        return total

    def _checkpoint_locked(self) -> None:
        conn = self._conn
        if conn is None:
            return
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError:
            logger.warning("Conversation history checkpoint failed", exc_info=True)
        self._chmod()

    def _chmod(self) -> None:
        for candidate in (
            self.path,
            Path(str(self.path) + "-journal"),
            Path(str(self.path) + "-wal"),
            Path(str(self.path) + "-shm"),
        ):
            if not candidate.exists():
                continue
            try:
                os.chmod(candidate, 0o600)
            except OSError:
                logger.warning("Conversation history cache chmod failed", exc_info=True)

    def _maintenance_loop(self) -> None:
        while not self._stop.wait(_MAINTENANCE_INTERVAL_SECONDS):
            try:
                self.maintain()
            except Exception:
                logger.warning("Conversation history maintenance failed", exc_info=True)


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _starts_with(items: list[JsonValue], prefix: list[JsonValue]) -> bool:
    if len(items) < len(prefix):
        return False
    return all(_items_equal(items[index], prefix[index]) for index in range(len(prefix)))


def _suffix_delta(history: list[JsonValue], incoming: list[JsonValue]) -> list[JsonValue]:
    if history and _starts_with(incoming, history):
        return incoming[len(history) :]
    return incoming


_CACHE: ConversationHistoryCache | None = None
_CACHE_GUARD = threading.Lock()


def get_conversation_history_cache() -> ConversationHistoryCache:
    global _CACHE
    with _CACHE_GUARD:
        if _CACHE is None:
            from app.core.config.settings import get_settings

            settings = get_settings()
            enabled = getattr(settings, "conversation_history_cache_enabled", False)
            if not isinstance(enabled, bool):
                enabled = False
            max_bytes = _settings_int(settings, "conversation_history_cache_max_bytes", 1024**3)
            conversation_max = _settings_int(
                settings,
                "conversation_history_cache_conversation_max_bytes",
                32 * 1024 * 1024,
            )
            idle = _settings_int(settings, "conversation_history_cache_idle_ttl_seconds", 1800)
            free = _settings_int(settings, "conversation_history_cache_min_free_disk_bytes", 512 * 1024 * 1024)
            data_dir = getattr(settings, "data_dir", None)
            path = Path(data_dir) / _CACHE_DB_NAME if isinstance(data_dir, Path) else Path(_CACHE_DB_NAME)
            _CACHE = ConversationHistoryCache(
                path,
                enabled=enabled,
                max_bytes=max_bytes,
                conversation_max_bytes=conversation_max,
                idle_ttl_seconds=idle,
                min_free_disk_bytes=free,
                start_maintenance=enabled,
            )
        return _CACHE


def set_conversation_history_cache(cache: ConversationHistoryCache | None) -> None:
    global _CACHE
    with _CACHE_GUARD:
        if _CACHE is not None and _CACHE is not cache:
            _CACHE.close()
        _CACHE = cache


def _settings_int(settings: object, name: str, default: int) -> int:
    value = getattr(settings, name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value if value > 0 or name.endswith("min_free_disk_bytes") else default


def cached_history_replay_available(previous_response_id: str | None) -> bool:
    """True when the process cache can rebuild ``previous_response_id``."""

    if not previous_response_id:
        return False
    try:
        return get_conversation_history_cache().holds_replayable_history(previous_response_id)
    except Exception:
        logger.warning("Conversation history availability check failed", exc_info=True)
        return False


def try_plan_history_replay(
    *,
    request_body: dict[str, JsonValue],
    reason: HistoryReplayReason,
    downstream_visible: bool,
    already_replayed: bool,
    owner_blocked: bool,
    file_pinned: bool,
    request_id: str | None = None,
) -> HistoryReplay | None:
    try:
        return get_conversation_history_cache().plan_replay(
            request_body=request_body,
            reason=reason,
            downstream_visible=downstream_visible,
            already_replayed=already_replayed,
            owner_blocked=owner_blocked,
            file_pinned=file_pinned,
            request_id=request_id,
        )
    except Exception:
        logger.warning("Conversation history replay planning failed", exc_info=True)
        return None


def observe_completed_turn(
    *,
    request_body: dict[str, JsonValue] | None,
    response_id: str | None,
    output_items: list[JsonValue] | None,
    conversation_id: str | None = None,
) -> None:
    if request_body is None or not response_id:
        return
    try:
        get_conversation_history_cache().record_completed_turn(
            request_body=request_body,
            response_id=response_id,
            output_items=output_items or [],
            conversation_id=conversation_id,
        )
    except Exception:
        logger.warning("Conversation history record failed", exc_info=True)


def request_body_from_text(request_text: str | None) -> dict[str, JsonValue] | None:
    if not request_text:
        return None
    try:
        parsed = json.loads(request_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def output_items_from_event_payload(payload: object) -> tuple[str | None, list[JsonValue]]:
    if not isinstance(payload, dict):
        return None, []
    response = payload.get("response")
    if not isinstance(response, dict):
        return None, []
    response_id = response.get("id") if isinstance(response.get("id"), str) else None
    output = response.get("output")
    if not isinstance(output, list):
        return response_id, []
    return response_id, output


def observe_responses_completion(payload: object, event: object, *, conversation_id: str | None = None) -> None:
    if getattr(event, "type", None) != "response.completed":
        return
    dump = getattr(payload, "model_dump", None)
    if not callable(dump):
        return
    try:
        body = dump(mode="json")
    except Exception:
        logger.warning("Conversation history record could not read the request", exc_info=True)
        return
    response = getattr(event, "response", None)
    response_id = getattr(response, "id", None) if response is not None else None
    output = getattr(response, "output", None) if response is not None else None
    items: list[JsonValue] = []
    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict):
                items.append(item)
                continue
            dumped = getattr(item, "model_dump", None)
            if not callable(dumped):
                continue
            value = dumped(mode="json")
            if isinstance(value, dict):
                items.append(value)
    if not isinstance(body, dict) or not isinstance(response_id, str):
        return
    observe_completed_turn(
        request_body=body,
        response_id=response_id,
        output_items=items,
        conversation_id=conversation_id,
    )


def maybe_apply_model_history_replay(
    payload: _MutableReplayPayload,
    *,
    request_id: str | None,
    reason: HistoryReplayReason,
    downstream_visible: bool,
    owner_blocked: bool,
    file_pinned: bool,
) -> HistoryReplay | None:
    """Mutate a Responses request in place when a full-history replay is available."""

    dump = getattr(payload, "model_dump", None)
    if not callable(dump):
        return None
    try:
        body = dump(mode="json")
    except Exception:
        logger.warning("Conversation history replay could not read the request", exc_info=True)
        return None
    if not isinstance(body, dict):
        return None
    replay = try_plan_history_replay(
        request_body=body,
        reason=reason,
        downstream_visible=downstream_visible,
        already_replayed=request_history_replayed(request_id),
        owner_blocked=owner_blocked,
        file_pinned=file_pinned,
        request_id=request_id,
    )
    if replay is None:
        return None
    try:
        payload.input = replay.request_body.get("input")
        payload.previous_response_id = None
        if replay.switch_account:
            payload.conversation = None
    except Exception:
        logger.warning("Conversation history replay could not update the request", exc_info=True)
        return None
    mark_request_history_replayed(request_id)
    return replay


def account_admission_blocks(balancer: object, account_id: str | None) -> bool:
    """True when the admission breaker will not give this account a new request."""

    if not account_id:
        return False
    from app.modules.proxy._load_balancer.admission_breaker import (
        AdmissionBreakerPolicy,
        blocks_new_assignment,
    )

    runtime_map = getattr(balancer, "_runtime", None)
    runtime = runtime_map.get(account_id) if isinstance(runtime_map, dict) else None
    return blocks_new_assignment(runtime, time.time(), AdmissionBreakerPolicy.from_settings())
