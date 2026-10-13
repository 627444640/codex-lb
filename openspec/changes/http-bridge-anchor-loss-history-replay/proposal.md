## Why

Production on v1.24.6: the HTTP responses bridge (client HTTP, upstream Codex websocket) rewrote `previous_response_not_found` to `stream_incomplete` ("Upstream websocket closed before response.completed") with `fresh_replay_available=false`, even when `conversation_history.db` already held the chain. In one hour, 74 of 76 real errors were that pair. The existing cache resend (`history_replay_reason=stream_incomplete`) succeeded 15/15, so the cache itself works. The direct WebSocket path already resends this terminal from the cache before it records `continuity_fail_closed`. The HTTP bridge did not.

## What Changes

- Before the HTTP bridge fail-closes an anchored `previous_response_not_found`, it resends the turn once from cached history when no model output has reached the client. The resend omits `previous_response_id` and records `history_replay_reason=previous_response_not_found`.
- A staged resend is not logged as `continuity_fail_closed` and does not mark the anchor stale.
- A cache miss, a spent retry, other pending requests, or model output already forwarded keeps the existing fail-closed terminal. The resend is one attempt; a failed send returns that terminal and does not try again.
- On the HTTP bridge only, `fresh_replay_available` is true when a retry-safe fresh body exists or the cache holds a replayable chain. Direct WebSocket diagnostics keep their historical meaning.
- A hard session stays on the owning account. An unavailable sticky owner is not reassigned.

## Capabilities

### Modified Capabilities

- `conversation-history-replay`: the HTTP responses bridge applies the one pre-output `previous_response_not_found` replay before fail-closed, and its stale-anchor diagnostic counts a cached chain.

## Impact

HTTP bridge upstream-event handling (`app/modules/proxy/_service/http_bridge/upstream_events.py`) and the shared stale-anchor diagnostic (`app/modules/proxy/_service/websocket/helpers.py`). No schema change, no new setting, no dashboard change.
