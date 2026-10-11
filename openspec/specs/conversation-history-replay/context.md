# Conversation history replay

## Purpose

Give the proxy a local copy of an in-flight conversation so a lost upstream response, or an owner the admission breaker has opened, can be resent as a self-contained turn.

## Decisions

The cache is a second SQLite file, `data_dir/conversation_history.db`. It is not `store.db`. Memory holds keys, sizes, response ids, and a short batch of already-compressed blobs. Conversation text is read from disk only while a replay body is built.

A turn is written once, when it completes. Token deltas are not written. New bytes are the suffix after the cached prefix. Commits are batched unless the next turn of the same conversation needs the previous row, or the projected file size would pass the cap.

The replay drops `previous_response_id`. It stays on the same account for `previous_response_not_found` and pre-output `stream_incomplete` while that account can still take the turn. It moves when the reason is `owner_unavailable` or the admission breaker blocks the owner. A file id, or a file pin, refuses the move. The strict account-neutral body check is not the gate: Codex requests carry extra fields, and that check would refuse almost every move.

The close still counts toward the admission breaker. `previous_response_not_found` is not an admission code.

Defaults are on: 1 GiB file cap, 32 MiB per conversation, 30 minute idle TTL, 512 MiB free-disk floor. Those knobs stay configurable because conversation size and disk headroom differ by host. They are not listed in `.env.example`. The journal is in memory, so a crash can drop turns that were not flushed.

## Constraints

File mode is `0600`. Evicted conversations are deleted and incremental vacuum returns their pages. The stats endpoint has no field for conversation text. Low free disk disables the cache, logs a warning, and does not raise.

## Failure modes

Over the per-conversation cap, that conversation is dropped. An incomplete chain is not replayed. A second failure on the same request is returned to the client. If the outer HTTP attempt budget is already spent, the original error is surfaced. Two replicas do not share the cache file.

## Example

Turn 1 completes on account A and is stored. Turn 2 names that response id. Upstream closes the websocket with code 1000 before any output. The proxy records the admission failure, waits briefly, and resends turn 2 on A with turn 1's items inline and no `previous_response_id`. If A's breaker is open, the same body goes to account B, unless the history contains a file id.
