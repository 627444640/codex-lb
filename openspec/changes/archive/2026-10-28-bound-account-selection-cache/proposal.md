## Why

Account-selection snapshots remain resident after expiry and even when caching is disabled. Distinct routing scopes can therefore retain an unbounded number of account snapshots between invalidations.

## What Changes

- Limit the selection cache to 256 resident scopes by default.
- Reclaim expired entries during reads and writes; retain no entries when TTL is zero.
- Preserve scope isolation, generation fencing, lease cleanup and existing routing outcomes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `account-routing`: bounded selection snapshot residency and unchanged invalidation semantics.

## Impact

Changes the process-local selection cache and adds resource-retention and public account-selection regressions. No API, schema, dependency or operator setting changes.
