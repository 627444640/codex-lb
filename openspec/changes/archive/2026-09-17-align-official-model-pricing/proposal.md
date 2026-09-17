## Why

Broad model-family aliases price Mini, Nano, Pro and Cyber variants as different models. Missing service-tier prices also fall back to Standard, and treating an unknown final price as zero can release a cost-limited request's entire reservation.

## What Changes

- Register verified model variants and refresh pricing provenance to the 2026-09-17 official table.
- Restrict built-in aliases to exact compatibility names and numeric dated snapshots, including published Daybreak targets.
- Keep unpublished model, tier and context prices unknown and expose a distinct unknown_pricing status.
- Reject unpriced admission for cost-limited keys; preserve the admitted allowance when upstream switches to an unpriced result, while settling token counters normally.
- Keep source-defined prices and explicit zero costs distinct from unknown costs; cover HTTP, WebSocket, image and source paths with regressions.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `api-keys`: Verified variant rates, bounded aliases and unknown-price quota protection.
- `images-api-compat`: Explicit modality rates for supported image variants.
- `proxy-runtime-observability`: Distinguish unavailable prices from unavailable models or usage.

## Impact

Six backend modules, dashboard schema and translations, regression tests and OpenSpec artifacts. The existing accounting and output-timing implementation is retained. No schema migration, new configuration flag, automatic price refresh or historical bill rewrite is introduced.
