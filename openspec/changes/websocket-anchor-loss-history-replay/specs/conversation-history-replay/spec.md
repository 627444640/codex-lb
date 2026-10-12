## MODIFIED Requirements

### Requirement: One pre-output full-history replay

The proxy SHALL cache completed turns of an in-flight conversation and, before any output event is forwarded to the client, SHALL resend the current turn at most once when upstream returns `previous_response_not_found`, ends the stream as `stream_incomplete` before the first output, or returns a pre-output admission failure (`server_error`, `server_is_overloaded`, `overloaded_error`, or HTTP 500 or higher) while the request still carries `previous_response_id`. The resend SHALL include the cached history, SHALL omit `previous_response_id`, and SHALL wait for a random delay between 50 and 250 milliseconds. The resend SHALL consume the same one-retry budget as admission failover. When the owning account is not admission-blocked and the failure is not an admission failure, the resend SHALL use that same account. When the owning account is admission-open, the failure is `previous_response_owner_unavailable`, or the failure is a pre-output admission failure, the resend SHALL use a different healthy account. A history that contains a file id, or a request pinned by a file, SHALL NOT move to another account. When the owning account cannot be resolved, the proxy SHALL NOT send the original `previous_response_id` to another account. After any output has been forwarded, the proxy SHALL NOT replay. A pre-output close that qualifies for the admission breaker SHALL still be recorded against that breaker, once. A second failure on the same request SHALL be returned to the client. The HTTP responses bridge SHALL apply this replay before it would otherwise fail an anchored pre-output turn.

On the direct Responses WebSocket, a `previous_response_not_found` terminal SHALL qualify both before `response.created` and after it, as long as upstream has sent only the `response.created` and `response.in_progress` lifecycle events for that turn and no model output. It SHALL qualify only when that request is the sole pending request on the upstream socket and carries no retry-safe client full resend. The proxy SHALL decide on this replay before it records the turn as a continuity fail-closed or marks the anchor as stale. A staged replay SHALL NOT emit a `continuity_fail_closed` event or mark the anchor as stale. When no replay is staged, the proxy SHALL return its existing fail-closed terminal unchanged.

#### Scenario: Lost previous response is resent on the same account
- **GIVEN** the cache holds the completed turns behind a `previous_response_id`
- **WHEN** upstream returns `previous_response_not_found` before any output
- **AND** the owning account is not admission-blocked
- **THEN** the proxy resends the turn once on that account
- **AND** the resend contains the cached history and no `previous_response_id`

#### Scenario: A 500 is resent without the anchor
- **GIVEN** the cache holds the completed turns behind a `previous_response_id`
- **AND** the history has no file id
- **WHEN** upstream returns `server_error` before any output
- **THEN** the proxy resends the turn once on a different healthy account
- **AND** the resend contains the cached history and no `previous_response_id`

#### Scenario: Open owner moves to a healthy account
- **GIVEN** the cache holds a full history with no file id
- **WHEN** the owning account is admission-open or returns `previous_response_owner_unavailable` before any output
- **THEN** the proxy resends the turn once on a different healthy account
- **AND** the resend contains the cached history and no `previous_response_id`

#### Scenario: Output already forwarded is not replayed
- **WHEN** a qualifying failure arrives after an output event was forwarded
- **THEN** the proxy does not resend the turn

#### Scenario: A file id does not move
- **GIVEN** the cached history or the current turn contains a file id
- **WHEN** the owning account is unavailable before any output
- **THEN** the proxy does not send the turn to a different account

#### Scenario: The close still counts
- **WHEN** upstream closes with code 1000 before any output and a history replay is staged
- **THEN** that close still counts toward the owning account's admission breaker

#### Scenario: WebSocket anchor loss after response.created is resent from cache
- **GIVEN** the cache holds the completed turns behind a direct WebSocket request's `previous_response_id`
- **AND** upstream has sent `response.created` for the turn and no model output
- **WHEN** upstream fails the turn with `previous_response_not_found`
- **THEN** the proxy resends the turn once with the cached history and no `previous_response_id`
- **AND** the client receives one `response.created` and the replayed turn under the original response id
- **AND** no `continuity_fail_closed` event is recorded for the turn

#### Scenario: WebSocket anchor loss without cached history fails closed
- **GIVEN** the cache holds no history for a direct WebSocket request's `previous_response_id`
- **WHEN** upstream returns `previous_response_not_found` before any output
- **THEN** the proxy does not resend the turn
- **AND** the client receives the existing fail-closed terminal
- **AND** the `continuity_fail_closed` event and stale-anchor diagnostics are recorded

#### Scenario: WebSocket anchor loss after model output is not replayed
- **GIVEN** the cache holds the history behind a direct WebSocket request's `previous_response_id`
- **WHEN** upstream returns `previous_response_not_found` after any model output for that turn
- **THEN** the proxy does not resend the turn

#### Scenario: WebSocket anchor loss is replayed once
- **GIVEN** a direct WebSocket request has already spent its one resend
- **WHEN** upstream returns `previous_response_not_found` before any output
- **THEN** the proxy does not resend the turn again
- **AND** the client receives the fail-closed terminal

### Requirement: Replays are logged and stats omit conversation text

The proxy SHALL log each history replay with its reason and the extra input tokens spent, and SHALL store that reason and token count on the request log. The reason SHALL be stored on the row that records the outcome of the resent attempt, even when a different task than the one that staged the resend finishes that attempt. A resent request SHALL write exactly one terminal request-log row, so that row's `status` records whether the resend succeeded. Historical rows MAY leave those columns null. The dashboard API SHALL expose `GET /api/accounts/conversation-history-cache` with whether the cache is enabled, the disabled reason, bytes used, the total cap, the per-conversation cap, entry count, hit count, replay count, idle TTL, and the free-disk floor. That response SHALL NOT include conversation text.

#### Scenario: A replay is recorded on the request log
- **WHEN** the proxy resends a turn from cached history
- **THEN** the request log stores the replay reason and the extra input tokens

#### Scenario: A WebSocket anchor-loss resend is countable
- **GIVEN** a direct WebSocket turn was resent from cached history after `previous_response_not_found`
- **WHEN** the resent attempt completes or fails on a new upstream socket
- **THEN** exactly one request-log row with `transport = websocket` is written for that request
- **AND** the row stores `history_replay_reason = previous_response_not_found`
- **AND** the row's `status` is `success` when the resend completed and `error` when it failed

#### Scenario: Replay reasons stay distinct on the request log
- **WHEN** a direct WebSocket turn is resent from cached history after a pre-output owner or admission failure
- **THEN** its request-log row stores that failure's replay reason
- **AND** the row does not store `previous_response_not_found`

#### Scenario: Cache stats contain no conversation text
- **WHEN** an operator calls `GET /api/accounts/conversation-history-cache`
- **THEN** the response includes size, cap, entries, hits, and replays
- **AND** the response does not include conversation text
