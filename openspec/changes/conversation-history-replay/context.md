# Conversation history replay

## Purpose

Give the proxy a local copy of an in-flight conversation so a lost upstream response, or an owner the admission breaker has opened, can be resent as a self-contained turn.

## Decisions

The cache is a second SQLite file, `data_dir/conversation_history.db`. It is not `store.db`, so a full cache cannot lock or grow the primary database. Memory holds keys, sizes, response ids, and a short batch of already-compressed blobs. Conversation text is read from disk only while a replay body is built.

A turn is written once, when `response.completed` arrives. Token deltas are not written. New bytes are the suffix after the cached prefix. Commits are batched (32 turns) unless the next turn of the same conversation needs the previous row, or the projected file size would pass the cap.

The replay drops `previous_response_id`. It stays on the same account for `previous_response_not_found` and pre-output `stream_incomplete` while that account can still take the turn. It moves when the reason is `owner_unavailable` or the admission breaker blocks the owner. A file id in the rebuilt input, or a file pin, refuses the move and keeps today's fail-closed behavior. `single_account` is unchanged because selection still has only one account.

Cross-account movement does not use the strict account-neutral body check. Codex requests carry extra fields, and that check would refuse almost every move. File ids are the hard gate.

The close still counts toward the admission breaker before the replay is staged. `previous_response_not_found` is not an admission code.

Defaults are on, with a 1 GiB file cap, a 32 MiB per-conversation cap, a 30 minute idle TTL, and a 512 MiB free-disk floor. Those four knobs stay configurable because conversation size and disk headroom differ by host. Hardcoding them would force a redeploy to change the cache. The path is derived from `data_dir`. Batch size and the vacuum interval are constants. None of these settings are listed in `.env.example`.

The journal is in memory. A crash can drop turns that were not flushed. The next request then follows the existing fail-closed path.

## Constraints

File mode is `0600`. Evicted conversations are deleted and incremental vacuum returns their pages. The stats endpoint and the dashboard schema have no field for conversation text. Low free disk disables the cache, logs a warning, and does not raise.

## Failure modes

Over the per-conversation cap, that conversation is dropped and later turns of it are not replayed. An incomplete chain (a `previous_response_id` the cache does not know) is not replayed. A second failure on the same request is returned to the client. If the outer HTTP attempt budget is already spent, the payload is left unchanged and the original error is surfaced. Two replicas do not share the cache file.

## Example

Turn 1 completes on account A and is stored. Turn 2 names that response id. Upstream closes the websocket with code 1000 before any output. The proxy logs the admission failure, waits briefly, and resends turn 2 on A with turn 1's user and assistant items inline and no `previous_response_id`. If A's breaker is open, the same body goes to account B, unless the history contains a file id.
