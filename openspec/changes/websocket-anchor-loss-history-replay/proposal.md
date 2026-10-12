## Why

Production on v1.24.5 (`0e0e5ffe`): at 16:02 two direct WebSocket turns logged `continuity_fail_closed surface=websocket_stream reason=previous_response_not_found fresh_replay_available=false`, and the client received `stream_incomplete`. The referenced previous response had been written to `conversation_history.db` (`turns`, seq 19) at 15:58, so a full-history replay was available but was not used.

The direct WebSocket relay tries the history cache for `previous_response_not_found` only before `response.created`. Upstream also reports a lost anchor as a `response.failed` after `response.created`. That accepted shape takes no replay branch: the accepted classifiers only recognize capacity and admission codes, so the turn fails closed even when the cache holds the conversation. In both shapes the proxy also records `continuity_fail_closed` and remembers the anchor as stale before it decides on a replay, so the logs show a fail-closed turn even when the replay succeeds.

## What Changes

- A direct WebSocket `previous_response_not_found` terminal, before any model output, resends the turn once from cached history without `previous_response_id`. This covers the pre-created shape and the accepted shape where only the `response.created` / `response.in_progress` prelude was seen.
- The resend stays on the same account unless the admission breaker blocks it. A blocked account moves the resend to another account, except where a file id or file pin forbids the move.
- The replay is planned before the stale-anchor fail-closed is recorded. A staged replay records no `continuity_fail_closed` and does not mark the anchor stale.
- A cache miss, a spent one-retry budget, other pending requests on the socket, or any model output keeps the existing fail-closed terminal.
- For an accepted turn whose prelude carried numeric sequences, the replay suppresses its own prelude. A replay frame that does not advance beyond the exposed sequence settles as `stream_incomplete` and closes downstream with 1011.
- The request-log row of a WebSocket resend records `history_replay_reason`. The resent attempt is finished by a new upstream reader task, which never saw the context-variable mark, so these rows were written with a null reason. The mark now rides on the request state.
- An anchor loss that fails closed while other requests are in flight on the same upstream socket appends `concurrent_requests=true` to its stale-anchor diagnostics (`failure_detail` and `continuity_fail_closed`).

## Capabilities

### Modified Capabilities

- `conversation-history-replay`: the direct WebSocket accepted-prelude shape of `previous_response_not_found` qualifies for the one pre-output replay, and a staged replay is not logged as fail-closed.
- `conversation-history-replay`: a resent request writes one request-log row that names the replay reason, and its `status` records the outcome.
- `responses-api-compat`: the direct WebSocket sequence rule gets a second narrow exception for that replay, and stale-anchor diagnostics mark concurrent requests.

## Impact

Direct WebSocket relay (`app/modules/proxy/_service/websocket/`), plus the shared request-state helper in `app/modules/proxy/_service/support.py`. The HTTP bridge keeps its own previous-response recovery; its rows also gain the reason when it stages a resend through the shared helper. No schema change, no new setting, no version bump.
