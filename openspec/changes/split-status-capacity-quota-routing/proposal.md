# Split capacity, low-quota warnings, and routability

## Why

The status page currently displays a weighted pool capacity percentage while
the quota component evaluates the lowest account window. When the pool has
41% weighted capacity but one account is at 13%, the collector marks the page
as degraded and renders the same `额度不足` text used for a pool with no
usable quota. Operators cannot tell whether the pool is serving traffic, has a
low-reserve warning, or is actually unable to route a request.

## What Changes

- Keep the seven-day weighted percentage as the pool-capacity signal.
- Make the quota component represent routability only: it is operational when
  at least one account is quota-ready, unknown when readiness is unknown, and
  outage only when no usable quota remains.
- Add a separate, non-blocking low-quota advisory that uses the configured
  20% threshold and never changes the page-level service status or creates an
  outage incident by itself.
- Reserve `额度不足` for a routability outage with no available quota.
- Preserve the public privacy boundary: the public API does not expose account
  counts, account identifiers, or per-account quota values.
- Add an authenticated Settings view with sanitized operator counters and the
  lowest remaining value so administrators can explain a public warning.

## Capabilities

### Modified Capabilities

- `status-page-management`: separate capacity, low-quota advisory, and
  routability semantics on the public page and in the authenticated Settings
  view.

## Impact

- Independent monitor collector, snapshot alert/readiness handling, public
  status rendering, and synthetic tests.
- Private monitor control response, dashboard status-page schema/service/UI,
  and localized copy for the operator summary.
- No source-account schema or quota accounting changes; no production
  deployment is implied by this change.
