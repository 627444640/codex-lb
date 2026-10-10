## ADDED Requirements

### Requirement: Public status exposes bounded request quality diagnostics
The public status response SHALL include a recent request-quality window separate
from the live request window. It SHALL provide sample counts, error percentage,
sample and error timestamps, and grouped error categories with counts, failure
shares, affected model names and a public FAQ slug when one exists. It MUST
exclude request IDs, account identifiers, client addresses, raw error messages,
credentials and unknown error-code strings.

#### Scenario: Current request window is idle but recent failures exist
- **WHEN** the live request window has no normal samples and the bounded recent
  window contains completed failures
- **THEN** the response SHALL retain the recent sample and failure counts and
  categories instead of returning only an empty request result
- **AND** the public page SHALL state that the live window is idle while showing
  the recent request-quality evidence

#### Scenario: Unknown error code is recorded
- **WHEN** a request log contains an error code outside the canonical category map
- **THEN** the public response SHALL classify it as an unknown/other category
- **AND** the original unknown code and raw message SHALL not appear publicly

#### Scenario: Deleted or probe request rows exist
- **WHEN** a request row is soft-deleted, marked as a non-normal internal request,
  comes from an external model source, or uses a Luna probe model
- **THEN** the row SHALL be excluded from public request-quality aggregates

### Requirement: Status page distinguishes infrastructure readiness from business quality
The status page SHALL label its calendar history as infrastructure readiness and
state that the metric excludes real model request outcomes. It SHALL present
request-quality severity and counts separately from readiness and SHALL preserve
the existing idle behavior that does not claim business success without a real
request.

#### Scenario: Infrastructure probes are healthy and recent requests are degraded
- **WHEN** readiness probes are operational and the request-quality window meets
  the configured attention threshold
- **THEN** the page SHALL show the readiness result separately and expose the
  request-quality attention state and category guidance

#### Scenario: Monitor sample is stale
- **WHEN** the latest monitor snapshot is stale or unavailable
- **THEN** the public response SHALL mark the status unknown and clear both live
  request and recent request-quality values rather than showing old green data

### Requirement: Public incident summary accounts for active incidents
The public status response SHALL include a bounded summary of recent request
incidents and SHALL count any still-open request incident even when it opened
before the recent summary window. The summary SHALL not change stored incident
rows or notification behavior.

#### Scenario: Older request incident remains open
- **WHEN** a request incident opened before the recent summary window remains
  unclosed
- **THEN** the summary SHALL report an active incident
- **AND** the page SHALL not state that there are no active request incidents

#### Scenario: Recent incidents are recovered
- **WHEN** request incidents in the recent window are all closed
- **THEN** the page SHALL show their recent count and latest recovered state while
  limiting the detailed list to a readable recent subset
