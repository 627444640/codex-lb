## Why

A pool with one hard-eligible account can still return `No available accounts` when that account enters generic transient-error backoff. The existing admission-breaker liveness rule covers only the breaker; it does not cover the separate generic backoff. One transient upstream burst can therefore turn a one-account deployment into a local outage even though the account remains otherwise eligible.

## What Changes

- Allow the sole hard-eligible account to serve as the bounded fallback when it is the only account in generic transient-error backoff and no other candidate exists.
- Apply the same liveness rule to sticky and pinned single-account selection paths that pass `allow_backoff_fallback=False`; the rule is about pool liveness, not a new ownership bypass.
- Keep hard states, quota, rate-limit, permissions, model capability, concurrency caps and request-level exclusions authoritative.
- Do not add multi-account recovery tokens, new settings, schema changes or a general force/fail-open flag; those remain a separate follow-up.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `account-routing`: a single hard-eligible account is not excluded solely by generic transient-error backoff.

## Impact

- Pure selection logic and focused unit tests.
- No database migration, API change, new setting or dashboard change.
- Multi-account pools retain the existing generic fallback behavior.
- GitHub tracking: #18 under #15. This is a narrow first stage, not full bounded recovery admission for all pools.
