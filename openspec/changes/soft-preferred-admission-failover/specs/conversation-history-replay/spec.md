## ADDED Requirements

### Requirement: Soft preferred follow-ups replay cached history before changing accounts

When a soft-preferred HTTP responses bridge follow-up carries `previous_response_id` and the preferred account's admission breaker blocks a new assignment, the proxy SHALL resend that turn on another healthy account only from cached conversation history. The resend SHALL omit `previous_response_id`, SHALL include the cached history, and SHALL record `history_replay_reason=owner_unavailable` on the request log. The resend SHALL consume the one shared retry with admission failover. When the cache does not hold a replayable chain for that `previous_response_id`, the proxy SHALL return HTTP 503 `account_admission_breaker_open` and SHALL NOT send the turn to another account. A history that contains a file id SHALL NOT be forwarded to another account. A hard session affinity SHALL NOT take this resend.

#### Scenario: Cached follow-up falls back without the anchor

- **GIVEN** the cache holds the completed turns behind a soft-preferred follow-up's `previous_response_id`
- **AND** the preferred account's admission breaker is open
- **AND** another healthy account is eligible
- **WHEN** the HTTP bridge selects an account
- **THEN** the turn is sent to the other account
- **AND** the sent body contains the cached history and no `previous_response_id`
- **AND** the request log stores `history_replay_reason=owner_unavailable`

#### Scenario: Follow-up without cached history is not forwarded

- **GIVEN** the cache holds no history for a soft-preferred follow-up's `previous_response_id`
- **AND** the preferred account's admission breaker is open
- **AND** another healthy account is eligible
- **WHEN** the HTTP bridge selects an account
- **THEN** the response is HTTP 503 `account_admission_breaker_open`
- **AND** the turn is not sent to the other account
