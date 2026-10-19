# Status-page management delta

## MODIFIED Requirements

### Requirement: Public status uses reduced capacity and daily availability

The public status response and display MUST keep the weighted seven-day
capacity percentage separate from quota routability. The capacity percentage
MUST NOT be interpreted as the minimum account value or as proof that every
account is eligible.

#### Scenario: Pool has capacity while one account is low

- **WHEN** weighted capacity is 41%, one known account is at 13%, and another
  active account is quota-ready
- **THEN** the capacity card remains a warning according to the existing
  60%/20% visual thresholds
- **AND** the routability component is operational
- **AND** the page does not use `额度不足` for this condition

## ADDED Requirements

### Requirement: Routability owns the quota outage state

The quota component MUST be operational when at least one active account has a
complete, fresh quota window. It MUST be unknown when eligibility cannot be
determined. It MUST be outage, with detail `额度不足`, only when there is no
active account or all known active accounts are exhausted and no ready account
remains.

#### Scenario: One exhausted account has a ready fallback

- **WHEN** at least one account is exhausted and at least one other account is
  quota-ready
- **THEN** quota routability remains operational
- **AND** the page does not create an outage incident for quota

#### Scenario: No account can route

- **WHEN** no active account is available or all known active accounts are
  exhausted
- **THEN** quota routability is outage
- **AND** the detail is `额度不足`

### Requirement: Low reserve is a non-blocking advisory

The monitor MUST expose a separate `quota_warning` advisory when the lowest
known remaining value is below `low_quota_percent` or an account is exhausted.
The advisory MUST NOT change the top-level page status, readiness history,
incident state, or email alerts. Its detail MUST describe low reserve or an
exhausted account without claiming that the whole pool has no quota.

#### Scenario: Low reserve does not degrade a healthy page

- **WHEN** quota is routable and the lowest remaining value is below 20%
- **THEN** `quota_warning` is degraded with low-reserve copy
- **AND** the top-level page remains operational when other blocking signals
  are healthy

### Requirement: Public quota data remains privacy-safe

The public response MUST NOT expose account counts, account identifiers,
per-account remaining values, or the internal pool object. It MAY expose the
privacy-safe quota and advisory component states and the existing weighted
capacity percentage and reset timestamp.

### Requirement: Operator quota detail is authenticated and sanitized

The loopback-authenticated monitor control response and dashboard Settings view
MUST expose sanitized aggregate quota detail including routability, active,
ready, unknown, exhausted, lowest remaining value, threshold, collected time,
and stale state. They MUST NOT expose account identifiers, plan rows, raw
source records, or credentials. Stale data MUST clear derived numeric values.
