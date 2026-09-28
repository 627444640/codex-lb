## Why

The deployed internal timing extension decodes every canonical HTTP/SSE output
block solely to identify nonempty output. This restores per-block work on the
verbatim relay path. The internal contract counts nonempty content, so replacing
that observation with an event counter would change TPS sample eligibility.

## What Changes

- Recognize a conservative, complete flat JSON shape for common canonical output
  frames without decoding the object; retain the existing parser for all other shapes.
- Preserve nonempty output counts, first-output timestamps, forwarded bytes,
  reasoning-first TTFT, and current sample thresholds.
- Add product-path and differential regression coverage plus a reproducible local
  benchmark. Performance results apply to the observation operation, not model speed.
- Prepare this independent feat branch on v1.24.2 for later integration alongside
  status-page settings in v1.24.3.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `proxy-runtime-observability`: add a no-full-decode observation contract for the
  common SSE frame shape while retaining identical timing evidence and fallback semantics.

## Impact

HTTP/SSE output observation and its tests only. No database migration, dependency,
configuration, dashboard, model-source, WebSocket, routing or settlement change.
The status-page work stays independent. v1.24.3 integration and deployment are later steps.
