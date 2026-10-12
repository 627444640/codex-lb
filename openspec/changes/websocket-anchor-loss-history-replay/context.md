# Context: WebSocket anchor loss uses the history cache

## Purpose

`conversation-history-replay` already promises one pre-output resend from cached history when upstream returns `previous_response_not_found`. The direct WebSocket relay kept that promise only for an error that arrived before `response.created`. This change makes the accepted shape (`response.created`, then a `response.failed` naming the lost anchor) take the same replay, and stops logging a staged replay as a fail-closed turn.

## Production evidence

- v1.24.5 (`0e0e5ffe`), 16:02: two `continuity_fail_closed` events with `surface=websocket_stream`, `reason=previous_response_not_found`, `fresh_replay_available=false`.
- The referenced previous response was in `conversation_history.db` (`turns`, seq 19) since 15:58, well inside the 30-minute idle TTL.
- The client received `stream_incomplete`.

`fresh_replay_available` describes only a client full resend (`fresh_upstream_request_text`); it never reflected the history cache.

## Decisions

- **Plan before fail-closed.** The replay is attempted first. Only when no replay is staged does the existing rewrite run, record `continuity_fail_closed`, and remember the anchor as stale. A staged replay must not leave a stale-anchor mark behind, because the next request with the same anchor would otherwise be suppressed.
- **Same predicate for both shapes.** One helper decides eligibility: anchored request, no retry-safe fresh body (that body has its own replay), one pending request, no replay spent, no model output, and no output reported by the terminal payload. Pre-created requests must have no response events. Accepted requests must be lifecycle-only.
- **Account choice follows the spec.** `previous_response_not_found` is not an account failure, so the resend stays on the same account and no health penalty is written. When the admission breaker blocks that account, the resend moves; a file id or file pin keeps it put (enforced by the cache planner).
- **Sequence safety.** On the direct WebSocket, `response.created` normally reaches the client with `sequence_number = 0`. The replay suppresses its own `response.created` and, when the original exposed one, its `response.in_progress`. The exposed watermark must be lower than the number of prelude events, so the first forwarded replay frame should advance past it. The existing regression check still guards the edge: a non-suppressed replay frame at or below the watermark settles as `stream_incomplete` and closes with 1011. The suppressed `response.in_progress` is now exempt from that check, like the suppressed `response.created`; it is never forwarded.
- **The responses-api-compat delta carries the prewarm exception.** `recover-sequenced-codex-prewarm` is implemented but not yet synced to the main spec. The modified requirement here includes its exception unchanged, so either change can archive first.

## Not covered

- An anonymous `previous_response_not_found` matched to several pending requests on one socket still fails each of them closed. Replaying several requests on one socket is out of scope.
- The HTTP bridge also logs `surface=websocket_stream` for this rewrite. It has its own previous-response recovery and is unchanged here. If a production occurrence came through the bridge (request log `transport=http`), this change does not alter it.

## Failure modes

- Cache miss, disabled cache, or a conversation over its cap: the existing fail-closed terminal and diagnostics are unchanged.
- One-retry budget already spent (admission failover, earlier replay): fail-closed.
- The replay itself fails: that failure is surfaced; there is no second replay because the resend carries no `previous_response_id`.
- Replay sequence does not advance: `stream_incomplete`, 1011 close, single settlement.

## Example

1. Turn 19 completes with `resp_19`; the cache records it.
2. The client sends turn 20 with `previous_response_id=resp_19`.
3. Upstream sends `response.created` (`sequence_number` 0, forwarded) and then `response.failed` with `previous_response_not_found`.
4. The proxy suppresses the failure, rebuilds the input from the cache, drops `previous_response_id`, and reconnects.
5. The replay's `response.created` is suppressed; its later frames are forwarded under the original response id with sequence numbers above 0.
6. The request log row records `history_replay_reason=previous_response_not_found`.
