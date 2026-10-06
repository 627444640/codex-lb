# Color the weekly capacity percentage with its energy meter

## Why

The weekly capacity card now uses green, yellow and red energy blocks, but the
large percentage value remains neutral. The value should reinforce the same
capacity state at a glance.

## What Changes

- Apply the energy meter's healthy, warning, critical and unknown classes to
  the large weekly percentage value.
- Preserve the existing percentage calculation, accessibility text and reset
  timestamp.
- Extend the DOM test to assert that the value and blocks share each threshold
  class.

## Impact

This is a presentation-only status-page change. No API, quota, incident or
monitoring behavior changes.
