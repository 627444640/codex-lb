## ADDED Requirements

### Requirement: Soft preferred accounts fail over while the breaker blocks them

When an HTTP responses bridge request names a preferred account that is only a soft preference, and that account's admission breaker is open or half-open with the probe already in flight, the proxy SHALL NOT assign that account. A soft preference SHALL mean the preferred account is not an ownership pin: the HTTP bridge session key strength is not `hard`, owner check is not applied, the request is not file-pinned, routing strategy is not `single_account`, and fallback when the preferred account is unavailable remains allowed. `previous_response_id` by itself SHALL NOT make the preference hard. The proxy SHALL select another healthy account, SHALL log `admission_failover` with reason `account_admission_breaker_open`, and SHALL record the account it left. A first turn that does not carry `previous_response_id` SHALL fall back directly. When no other healthy account can take the turn, the proxy SHALL return HTTP 503 `account_admission_breaker_open` with message "No available accounts". A disabled admission breaker SHALL leave this selection unchanged. A half-open account whose probe slot is free SHALL remain eligible for that probe. An ownership pin, including key strength `hard`, owner check applied, `require_same_account`, a file pin, and `single_account` routing, SHALL stay on the pinned account. A hard Codex session owner that is not an ownership pin SHALL still fail with HTTP 503 `account_admission_breaker_open` and SHALL NOT be served by another account.

#### Scenario: Soft preferred breaker open uses another healthy account

- **GIVEN** account A is the soft preferred account and its admission breaker is open
- **AND** account B is eligible and not admission-blocked
- **AND** the request does not carry `previous_response_id`
- **WHEN** the proxy selects an account
- **THEN** the request is served by account B
- **AND** the failover from account A is recorded with reason `account_admission_breaker_open`

#### Scenario: Soft preferred breaker open with no other healthy account returns 503

- **GIVEN** account A is the soft preferred account and its admission breaker is open
- **AND** no other healthy account is eligible
- **WHEN** the proxy selects an account
- **THEN** the response is HTTP 503 `account_admission_breaker_open`

#### Scenario: Half-open probe already taken falls back

- **GIVEN** account A is the soft preferred account
- **AND** its admission breaker is half-open and the probe is already in flight
- **AND** account B is eligible and not admission-blocked
- **WHEN** the proxy selects an account
- **THEN** the request is served by account B

#### Scenario: Hard Codex owner stays unavailable

- **GIVEN** a hard Codex session owner mapping names account A
- **AND** that mapping is not an ownership pin
- **AND** account A's admission breaker is open
- **AND** account B is eligible
- **WHEN** the proxy selects an account
- **THEN** the response is HTTP 503 `account_admission_breaker_open`
- **AND** the request is not served by account B

#### Scenario: Ownership pin stays on the open account

- **GIVEN** the preferred account is an ownership pin whose admission breaker is open
- **AND** another healthy account is eligible
- **WHEN** the proxy selects an account
- **THEN** the pinned account is still selected

#### Scenario: Disabled breaker keeps the preferred account

- **GIVEN** the admission breaker is disabled
- **AND** the soft preferred account would otherwise be admission-open
- **WHEN** the proxy selects an account
- **THEN** the preferred account is selected
