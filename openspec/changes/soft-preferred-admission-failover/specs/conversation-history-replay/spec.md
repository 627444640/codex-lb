## ADDED Requirements

### Requirement: Soft preferred follow-ups replay cached history before changing accounts

A soft-preferred follow-up with `previous_response_id` SHALL move to another account only by replaying cached history. The resend SHALL omit `previous_response_id`, SHALL include that history, and SHALL record `history_replay_reason=owner_unavailable`. If the cache has no replayable chain, or the chain contains a file id, the proxy SHALL return HTTP 503 `account_admission_breaker_open` and SHALL NOT forward the turn. A hard session SHALL NOT take this resend.

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
