## MODIFIED Requirements

### Requirement: Continuity is not switched

The proxy SHALL NOT move a request to another account when a file pin requires that account, or when routing strategy is `single_account`. A request that depends on a `previous_response_id` SHALL stay on the owning account unless a cached full-history replay resends that turn without the anchor. Without that replay, the request SHALL fail on the owning account.

#### Scenario: previous_response_id stays on the owner without cached history
- **GIVEN** a request carries a `previous_response_id` owned by an account whose admission breaker is open
- **AND** the proxy has no cached full history for that response
- **WHEN** the proxy selects an account
- **THEN** the request is not sent to a different account

#### Scenario: cached history may leave an open owner
- **GIVEN** a pre-output failure on a previous_response owned by an admission-open account
- **AND** the cache holds the full history and the history has no file id
- **WHEN** the proxy replays the turn
- **THEN** the resend omits `previous_response_id`
- **AND** the resend may use a different healthy account
