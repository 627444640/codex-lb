## ADDED Requirements

### Requirement: Bridge gate diagnostics separate refusal from upstream execution

Bridge admission diagnostics MUST distinguish active cooldown, half-open occupancy, recovery-generation conflict and unavailable recovery state. A request refused before dispatch MUST NOT be logged as a newly executed upstream timeout. Diagnostics MUST preserve existing physical-attempt deduplication and MUST NOT expose raw affinity keys, credentials, proxy URLs, private request payloads or conversation content. Metrics MUST use bounded reason labels rather than request, session, operation or generation identifiers.

#### Scenario: A restored durable cooldown is observable without another send
- **GIVEN** the proxy loads an active cooldown written by a previous process or another replica
- **WHEN** a request is refused by that cooldown
- **THEN** the request diagnostics identify the bridge admission gate and genuine remaining deadline
- **AND** the record does not imply that this refusal created an upstream request

#### Scenario: A busy probe has a distinct diagnostic reason
- **GIVEN** a circuit has no future cooldown deadline and its half-open probe is occupied
- **WHEN** another request is refused
- **THEN** the diagnostic reason identifies half-open occupancy
- **AND** a cooldown duration is not fabricated

#### Scenario: Sensitive identities are absent from review evidence
- **WHEN** automated tests and review evidence are prepared for this change
- **THEN** their failure sequences use synthetic request and account identities
- **AND** no production database, credential, environment file, raw conversation or machine-specific snapshot is included in published evidence
