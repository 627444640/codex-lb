## Why

Request logs omit costs for current model names, round small nonzero amounts
to zero, discard cache-write usage, and lose or misattribute usage on failed
SSE and image requests. Operators need reproducible estimates with explicit
unknowns instead of apparently complete or zero costs.

## What Changes

- Update verified model prices, tier/long-context rules and cache-write rates.
- Persist cache-write usage and upstream pricing-model identity without adding
  cached or reasoning subsets to total tokens twice.
- Capture reported usage on failed terminal events and store image-tool usage
  with the image model, including streaming/edit paths and rollup consistency.
- Show small request costs precisely and distinguish unknown or incomplete
  estimates; keep aggregate totals explicit about their known-only scope.
- Preserve historical stored amounts and expose their estimate provenance;
  never invent missing historical usage or a price for opaque model aliases.

## Impact

Pricing, request-log persistence/API, proxy terminal accounting, image usage,
dashboard display and an additive database migration. Existing success-only
API-key settlement policy and routing/account ownership remain unchanged.
Private deployment files and production credentials are outside this change.
