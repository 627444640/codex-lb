# Render weekly capacity as energy blocks

## Why

The seven-day capacity card currently uses a continuous browser progress bar.
The status page design calls for a segmented energy-meter treatment that makes
remaining capacity easier to scan and keeps the visual language consistent with
the compact status cards.

## What Changes

- Replace the native continuous progress bar with a 24-block energy meter.
- Fill blocks according to the weighted seven-day percentage and show empty
  blocks for the remaining capacity.
- Keep the existing percentage, reset time, unknown state and keyboard/screen
  reader progress semantics.
- Add a DOM-level regression test for block count, filled-block rounding and
  accessible progress values.

## Impact

This is a public status-page presentation change. The API field, percentage
calculation, reset timestamp and capacity semantics remain unchanged.
