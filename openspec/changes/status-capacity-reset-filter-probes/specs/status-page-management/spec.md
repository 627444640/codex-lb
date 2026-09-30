## MODIFIED Requirements

### Requirement: Public status uses reduced capacity and daily availability

The independent public response and display SHALL expose only the
capacity-weighted remaining seven-day percentage, the earliest valid reset
timestamp for an applicable seven-day window, and the existing daily
availability data. It SHALL never expose account counts or per-account
capacity-readiness counters. When no applicable fresh reset is known, the
reset timestamp MUST be null. The display SHALL render daily probe
availability as a calendar heatmap with Asia/Taipei dates, distinguish days
without valid samples, center announcements in a full-width top row, and place
incident history in a full-width bottom section.

#### Scenario: Weekly reset is shown with capacity

- **WHEN** a fresh applicable seven-day window has a reset timestamp
- **THEN** the public capacity object includes `weekly_next_reset_at`
- **AND** the seven-day card displays the timestamp in Asia/Taipei time

#### Scenario: Weekly reset is unknown

- **WHEN** the weighted capacity is incomplete or no applicable fresh reset is
  available
- **THEN** `weekly_next_reset_at` is null
- **AND** the page shows an unknown reset value without inventing a date

### Requirement: Probe-only Luna traffic does not create normal request incidents

The monitor SHALL exclude request-log rows whose model name contains `luna`,
case-insensitively, from normal request totals, error rates, timing metrics
and request-component alert transitions. Existing `request_kind` and
model-source exclusions SHALL remain in force. Historical incidents and email
events SHALL NOT be rewritten solely by this change.

#### Scenario: Luna probe errors are excluded

- **WHEN** the source database contains only Luna-model error rows in the
  request window
- **THEN** the public request aggregate has no normal request errors
- **AND** the request component does not open a degraded/outage incident

#### Scenario: Non-Luna service errors remain observable

- **WHEN** the same request window contains a non-Luna model error
- **THEN** that error remains in the request aggregate and existing debounce
  rules continue to govern request incidents
