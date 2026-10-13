## Purpose

Stop the HTTP responses bridge from failing a continuation closed when the history cache can rebuild the lost `previous_response_id`.

## Decisions

Plan the resend before `_maybe_rewrite_websocket_previous_response_not_found_event`. That rewrite records `continuity_fail_closed` and, when `fresh_replay_available` is false, remembers the anchor as stale. A cache hit that is actually sent must not take that path.

Use the same candidate and stager as the direct WebSocket anchor-loss replay (`previous_response_not_found`, one shared retry, same account unless the admission breaker blocks the owner). Send through the existing HTTP `_retry_http_bridge_precreated_request` after resetting an accepted lifecycle to pre-created, so the replay suppresses its own prelude and does not duplicate `response.created`.

`fresh_replay_available` on `transport=http` includes the cache. Direct WebSocket diagnostics stay "retry-safe fresh body only", because those tests and the responses-api-compat requirement describe that meaning.

A failed send restores `previous_response_id` for the diagnostic, sets `replay_count` to at least 1, and falls through to the original terminal. The client is not left waiting, and a later close cannot send a second time.

## Constraints

No bytes of model output may already have been forwarded. Lifecycle prelude (`response.created` / `response.in_progress`) is allowed, matching the WebSocket path, because the replay suppresses that prelude. One retry, shared with admission failover.

Hard Codex session affinity stays owner-bound. `hard_continuity_anchor` remains set, so the reconnect uses `require_same_account`. Switching an unavailable sticky owner would violate the sticky-session spec ("Unavailable hard Codex owner does not lose its mapping") and is out of scope.

## Failure modes

Cache miss: original `stream_incomplete` terminal, `fresh_replay_available=false`, anchor marked stale. Output already forwarded: same terminal, no resend, and `fresh_replay_available=true` when the cache still holds the chain, so the anchor is not marked stale and a later turn can still replay. Send failure: original terminal, retry consumed. Another pending request on the socket: no resend.

## Example

Turn 1 completes and is stored under `resp-1`. Turn 2 is an HTTP bridge continuation with `previous_response_id=resp-1` and input "more". Upstream returns `previous_response_not_found` before any output. The bridge resends once on the same account with "kept" and "more" and no `previous_response_id`. The request log stores `history_replay_reason=previous_response_not_found`. The client does not receive `stream_incomplete`.
