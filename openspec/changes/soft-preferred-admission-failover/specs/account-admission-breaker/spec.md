## ADDED Requirements

### Requirement: Soft preferred accounts fail over while the breaker blocks them

When a soft-preferred account's admission breaker blocks a new assignment, the proxy SHALL select another healthy account and SHALL log `admission_failover` with reason `account_admission_breaker_open`. A first turn without `previous_response_id` SHALL fall back directly. With no other healthy account, the proxy SHALL return HTTP 503 `account_admission_breaker_open` and message "No available accounts".

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

### Requirement: Soft preference is distinct from an ownership pin

A preferred account SHALL be soft only when key strength is not `hard`, owner check is not applied, the request is not file-pinned, routing is not `single_account`, and preferred-account fallback remains allowed. `previous_response_id` alone SHALL NOT make it hard. An ownership pin SHALL stay pinned. A hard Codex owner that is not an ownership pin SHALL return HTTP 503 `account_admission_breaker_open` and SHALL NOT use another account.

#### Scenario: Ownership pin stays on the open account

- **GIVEN** the preferred account is an ownership pin whose admission breaker is open
- **AND** another healthy account is eligible
- **WHEN** the proxy selects an account
- **THEN** the pinned account is still selected

#### Scenario: Hard Codex owner stays unavailable

- **GIVEN** a hard Codex session owner mapping names account A
- **AND** that mapping is not an ownership pin
- **AND** account A's admission breaker is open
- **AND** account B is eligible
- **WHEN** the proxy selects an account
- **THEN** the response is HTTP 503 `account_admission_breaker_open`
- **AND** the request is not served by account B

### Requirement: A disabled breaker and a free probe keep the preferred account

A disabled admission breaker SHALL keep the preferred account. A half-open account whose probe slot is free SHALL stay eligible for that probe.

#### Scenario: Disabled breaker keeps the preferred account

- **GIVEN** the admission breaker is disabled
- **AND** the soft preferred account would otherwise be admission-open
- **WHEN** the proxy selects an account
- **THEN** the preferred account is selected

#### Scenario: Half-open free probe keeps the preferred account

- **GIVEN** account A is the soft preferred account
- **AND** its admission breaker is half-open and the probe slot is free
- **AND** account B is eligible
- **WHEN** the proxy selects an account
- **THEN** account A is still selected
