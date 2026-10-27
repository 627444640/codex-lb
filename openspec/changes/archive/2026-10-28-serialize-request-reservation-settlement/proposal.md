## Why

HTTP bridge detach, terminal finalization and abort cleanup can concurrently read the same live API-key reservation and issue redundant settlement writes. The seeded lifecycle test currently marks this as an expected failure: database compare-and-set preserves the outcome, but extra round trips remain.

## What Changes

- Serialize reservation release/finalization for one request state.
- Preserve retryable ownership when a write fails or is cancelled.
- Keep account-health writes after confirmed settlement and retain database idempotency.
- Convert the known duplicate-write canary into a passing regression.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `api-keys`: concurrent transport cleanup shares reservation ownership rather than submitting duplicate successful writes.

## Impact

Touches request-state bookkeeping and reservation settlement in the proxy. No schema, settings, wire protocol or routing policy changes.
