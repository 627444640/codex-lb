## ADDED Requirements

### Requirement: A sole eligible account survives generic transient backoff

When an account is the only hard-eligible candidate and the only reason it is unavailable is the generic transient-error backoff, foreground selection SHALL return that account rather than `No available accounts`. The exception SHALL NOT bypass hard account states, quota, rate limits, permissions, model capability, concurrency caps, or request-level exclusions. It SHALL NOT clear the recorded error count or shorten the backoff deadline.

#### Scenario: One active account in transient backoff remains selectable
- **GIVEN** exactly one hard-eligible active account
- **AND** its generic error count and last-error time place it inside the transient backoff window
- **WHEN** foreground selection runs
- **THEN** the selector returns that account
- **AND** the account's error count and last-error timestamp remain unchanged

#### Scenario: Sticky single-account selection keeps the only owner
- **GIVEN** the same sole account is the sticky or pinned owner
- **AND** the caller disallows ordinary backoff fallback
- **WHEN** selection runs for that owner
- **THEN** the selector still returns the sole account
- **AND** no different account is introduced

#### Scenario: Hard-ineligible sole account is not revived
- **GIVEN** exactly one account whose status is paused, deactivated, re-authentication-required, rate-limited, or quota-exceeded
- **WHEN** foreground selection runs
- **THEN** the selector does not return that account
- **AND** the existing hard-state error behavior is preserved

#### Scenario: Multi-account pools keep existing exclusion
- **GIVEN** two or more hard-eligible accounts
- **AND** one is in generic transient backoff
- **WHEN** selection runs with ordinary fallback rules
- **THEN** the existing multi-account exclusion/fallback behavior is unchanged
