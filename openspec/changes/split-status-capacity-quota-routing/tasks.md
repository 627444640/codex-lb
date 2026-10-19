## 1. OpenSpec and contracts

- [x] Create proposal, design, delta spec, and task artifacts before code edits.
- [x] Sync the normative status-page specification with the separated state
  model and operator detail contract.

## 2. Monitor state semantics

- [x] Separate routability from low-reserve advisory in collector snapshots.
- [x] Keep advisory components out of page severity, readiness, incidents, and
  email alerts while preserving routing outage behavior.
- [x] Add a sanitized authenticated operator quota summary without exposing
  account identifiers or raw pool rows.

## 3. Public and operator presentation

- [x] Update public labels and copy so `额度不足` only describes no routeable
  quota and low reserve is visibly advisory.
- [x] Render the sanitized quota summary in the authenticated Settings page.
- [x] Add matching localized copy and preserve accessible state text.

## 4. Regression coverage

- [x] Cover low reserve with ready accounts, exhausted fallback, true outage,
  unknown/stale snapshots, public privacy, alert exclusion, and internal
  summary shape.
- [x] Cover DOM capacity warning, low-reserve advisory, routability labels,
  and top-level status behavior.

## 5. Verification

- [x] Run monitor Python tests, UI tests, backend status-page tests, frontend
  tests, lint/format/syntax checks, and final diff review.
- [x] Run available OpenSpec validation or record the CLI-unavailable
  limitation with manual artifact/spec checks.
