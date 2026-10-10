# Make request quality visible when the current window is idle

## Why

The public page currently shows only the latest 15-minute request window. When
that window has no traffic, it renders an operational banner with no request
sample even when the recent service history contains repeated model failures.
The page's readiness calendar also measures only the gateway probe, so its
99.99% value can be read as business success. Recent production evidence shows
that this hides the most frequent failure classes: generic upstream processing
errors, incomplete streams, upstream overload, and continuation ownership
failures.

## What Changes

- Add a bounded, public-safe 24-hour request-quality summary with total samples,
  success/cancelled/error counts, window timestamps, last error time, and
  grouped error categories. Preserve the existing 15-minute live request card.
- Map known error codes into stable, user-actionable categories and expose only
  category labels, counts, percentages, affected model names and guidance; do
  not expose request IDs, account identifiers, client IPs, raw messages or
  credentials.
- Label the calendar metric as infrastructure readiness and explain that it
  excludes model request outcomes. Add a separate request-quality summary so an
  idle current window does not erase recent evidence.
- Replace repeated generic request incidents in the public display with a
  compact incident summary that shows the recent count, latest state, time
  window and top category. Keep stored incident and email behavior unchanged.
- Keep Luna probe filtering, idle status semantics, stale-data behavior and
  private control boundaries intact.

## Impact

This changes the monitor's public JSON contract and status-page presentation.
It does not change gateway routing, source request records, alert thresholds,
database schema, or email delivery semantics.
