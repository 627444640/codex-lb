## Why

Concurrent requests for the same uncached routing scope can all perform the same account and usage reads before any one of them fills the cache. Coalescing this work reduces cold-cache database amplification without sharing an AsyncSession or changing routing eligibility.

## What Changes

- Keep the existing lock-free cache-hit path.
- Coordinate cache misses per scope and recheck the cache after acquiring load ownership.
- Retire coordination entries when the last owner/waiter exits, including cancellation.
- Preserve cache generation fencing and independent progress for different scopes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `account-routing`: coalesce concurrent loads for one cache-enabled selection scope.

## Impact

Selection cache internals and the existing selection-input loader. No schema, operator setting, upstream protocol or per-request eligibility changes.
