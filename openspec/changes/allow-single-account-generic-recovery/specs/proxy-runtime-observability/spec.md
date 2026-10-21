## ADDED Requirements

### Requirement: Single-account recovery fallback is observable

When foreground selection uses the sole-active-account generic-backoff liveness fallback, the proxy SHALL emit one structured observation containing the account id, the fixed reason `single_account_generic_backoff`, the account's error count, and the non-negative remaining backoff duration. The observation SHALL NOT contain request text, payloads, raw affinity keys, credentials, proxy URLs or conversation content. Emitting the observation SHALL NOT change selection, retry, timing or account health.

#### Scenario: Liveness fallback records its reason
- **GIVEN** exactly one active account is in generic transient backoff
- **WHEN** selection returns that account through the liveness exception
- **THEN** one `account_selection_recovery_fallback` observation is emitted
- **AND** it identifies the account and the fixed liveness reason
- **AND** it includes the error count and a non-negative remaining backoff

#### Scenario: Normal selection does not claim a recovery fallback
- **GIVEN** a healthy account is selectable normally
- **WHEN** selection returns it
- **THEN** no single-account recovery-fallback observation is emitted

#### Scenario: Observation does not expose private content
- **WHEN** the fallback observation is emitted
- **THEN** it contains no prompt, request body, affinity key, credential or proxy URL
- **AND** the observation does not alter the selected account or its backoff timestamps
