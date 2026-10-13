## ADDED Requirements

### Requirement: FAQ documents upstream response-protection failures

The published FAQ SHALL include a stable guide for the exact signature
`response protection is unavailable` and SHALL identify its public code as
`internal_error`. The guide MUST describe the observed boundary as an upstream
stream failure after gateway account selection, and MUST distinguish confirmed
evidence from the still-unknown upstream component. It MUST NOT publish raw
request IDs, account identifiers, client addresses, credentials, full request
bodies or raw log lines.

#### Scenario: Visitor opens the response-protection guide

- **WHEN** a visitor opens the FAQ
- **THEN** the page contains a published stable anchor for the exact signature
- **AND** the guide provides a bounded retry, alternate-account/model check and
  redacted escalation path
- **AND** the guide states that health checks or a restart alone do not prove
  authenticated model recovery

### Requirement: FAQ seed upgrades preserve administrator content

When the FAQ seed version advances, the monitor SHALL add the new response-
protection guide to an existing database without overwriting existing guide
content, status, revisions, withdrawals or deletions. New and upgraded
monitors SHALL expose the same published guide.

#### Scenario: Existing monitor upgrades from the previous seed

- **WHEN** the monitor starts with the previous seed marker and an existing
  guide database
- **THEN** it adds the new guide exactly once
- **AND** existing guide edits and deleted rows remain unchanged
