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

### Requirement: Soft preferred replay spends the one shared retry

A soft-preferred history replay SHALL consume the request's one transparent retry, shared with later account switching and resend. After that replay is sent, a pre-output upstream failure on the fallback account SHALL be forwarded to the client. The proxy SHALL NOT select another account or replay the turn again, and SHALL keep only that one failover and one history replay.

#### Scenario: Pre-output failure on the fallback account is not replayed

- **GIVEN** a soft-preferred follow-up was replayed from cache onto a fallback account because the preferred account's admission breaker is open
- **AND** a third healthy account is eligible
- **WHEN** the fallback account's upstream fails before the first output byte
- **THEN** the client receives that upstream error
- **AND** no further account is selected and the turn is not replayed
- **AND** exactly one admission failover and one history replay are recorded
