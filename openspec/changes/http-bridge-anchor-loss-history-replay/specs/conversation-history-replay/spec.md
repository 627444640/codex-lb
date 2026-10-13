## ADDED Requirements

### Requirement: HTTP bridge anchor loss resends cached history once

The HTTP responses bridge SHALL, before it records a continuity fail-closed for `previous_response_not_found`, resend an anchored turn at most once from cached conversation history when the cache holds a complete chain for that `previous_response_id`, the turn is the only pending request on the upstream socket, and no model output has been forwarded to the client. The resend SHALL omit `previous_response_id`, SHALL include the cached history, and SHALL stay on the same account unless the admission breaker blocks that account. The request log for that resend SHALL store `history_replay_reason=previous_response_not_found`. A resend that is sent SHALL NOT emit `continuity_fail_closed` and SHALL NOT mark the anchor stale. The resend SHALL consume the one shared retry. When the cache does not hold the chain, model output was already forwarded, or the resend cannot be sent, the bridge SHALL return the existing fail-closed terminal and SHALL NOT send the turn again. On that HTTP fail-closed path, `fresh_replay_available` SHALL be true when the cache holds a replayable chain for the anchor and false when it does not. Direct WebSocket stale-anchor diagnostics SHALL keep reporting `fresh_replay_available` only for a retry-safe fresh body. A hard session affinity SHALL NOT move to a different account because the sticky owner is unavailable.

#### Scenario: Cached HTTP anchor loss is resent once

- **GIVEN** the cache holds the completed turns behind an HTTP bridge request's `previous_response_id`
- **AND** no model output has been forwarded
- **WHEN** upstream returns `previous_response_not_found`
- **THEN** the bridge resends the turn once on the same account
- **AND** the resend contains the cached history and no `previous_response_id`
- **AND** the request log stores `history_replay_reason=previous_response_not_found`
- **AND** the client does not receive the fail-closed terminal
- **AND** no `continuity_fail_closed` event is recorded for that resend

#### Scenario: HTTP anchor loss without cached history fails closed

- **GIVEN** the cache holds no history for an HTTP bridge request's `previous_response_id`
- **WHEN** upstream returns `previous_response_not_found` before any output
- **THEN** the bridge does not resend the turn
- **AND** the client receives the existing `stream_incomplete` terminal
- **AND** the stale-anchor diagnostic reports `fresh_replay_available=false`

#### Scenario: HTTP anchor loss after model output is not replayed

- **GIVEN** the cache holds the history behind an HTTP bridge request's `previous_response_id`
- **WHEN** upstream returns `previous_response_not_found` after model output was forwarded
- **THEN** the bridge does not resend the turn
- **AND** the client receives the existing fail-closed terminal
- **AND** the stale-anchor diagnostic reports `fresh_replay_available=true`

#### Scenario: A failed HTTP resend is not attempted again

- **GIVEN** the cache holds the history behind an HTTP bridge request's `previous_response_id`
- **AND** the replacement send does not succeed
- **WHEN** upstream returns `previous_response_not_found` before any output
- **THEN** the client receives the existing fail-closed terminal
- **AND** the bridge does not send the turn a second time
