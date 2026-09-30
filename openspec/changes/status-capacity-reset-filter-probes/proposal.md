# Show the weekly reset time and exclude Luna probes from incidents

## Why

The public status page shows the weighted remaining seven-day capacity but not
when the next applicable window resets. Operators need that timestamp to
interpret a degraded percentage. The monitor also treats Luna-model probe
traffic as ordinary service traffic, so probe failures can create misleading
request errors and incident records.

## What Changes

- Return the earliest valid seven-day reset timestamp alongside the weighted
  remaining percentage and render it in the seven-day capacity card.
- Exclude model names containing `luna` from the monitor's normal request
  aggregation, error-rate calculation and request incident transitions.
- Keep the existing `request_kind` and model-source filters, and preserve
  historical monitor events rather than deleting them without durable model
  attribution.
- Add regression coverage for reset timestamps and Luna-only error samples.

## Impact

This changes only the independent monitor's public aggregate response and
event inputs. It does not change gateway routing, request-log retention, quota
accounting, or the upstream requests themselves. Historical incidents remain
available for audit; the new filter applies to subsequent snapshots.
