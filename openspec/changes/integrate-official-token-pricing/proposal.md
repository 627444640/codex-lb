## Why

Official pricing fixes developed against the earlier release must integrate with the current pricing catalog and quota lifecycle. Family aliases, missing cache-write/modality evidence and unpriced-tier fallbacks can misstate cost or release an unknown-cost request's entire allowance.

## What Changes

- Integrate verified model/variant prices, bounded aliases and explicit unknown prices into the current catalog without removing automatic metadata updates or explicit tier/context prices.
- Preserve actual model, cache-write and image modality evidence through request logs and quota settlement, with pricing provenance and unchanged historical totals.
- Reject unpriced cost-limited admission and retain the admitted allowance if the final price becomes unknown; keep custom-source and explicit-zero pricing separate.
- Expose distinct unknown/incomplete/historical cost states and accurate small amounts.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `api-keys`: Verified prices and conservative unknown-cost handling.
- `upstream-metadata`: Catalog-compatible cache-write and modality fields, bounded aliases and pricing provenance.
- `proxy-runtime-observability`: Usage evidence, cost precision and unknown pricing status.
- `images-api-compat`: Public image usage and distinct modality prices.

## Impact

Pricing, catalog adapters/snapshot, proxy accounting, quota settlement, nullable request-log metadata, dashboard display and regression tests. Existing routing, authentication, metrics and macOS operations changes are outside scope. The metadata migration must extend the current main Alembic head. Merge requires current-head cloud CI, CodeRabbit review resolution and a clean PR state.
