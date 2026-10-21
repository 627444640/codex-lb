## Context

Tracking: #18 under #15.

`select_account` already distinguishes generic error backoff from hard account states. It also has a fallback for multiple backoff candidates or a hard-blocked sibling, but deliberately requires `allow_backoff_fallback=True`. Sticky and pinned paths pass `False` to avoid moving ownership, so a one-account pool can still fail closed when only generic backoff is active.

## Goals / Non-Goals

**Goals:** keep a one-account pool live when the only blocker is generic transient backoff; preserve all hard eligibility and request-level exclusion rules.

**Non-Goals:** add a multi-account recovery token, alter admission-breaker policy, change retry counts or timing, add settings/schema/API, or bypass ownership/quota/caps.

## Decisions

1. The liveness exception is limited to exactly one total candidate and that candidate being in generic error backoff. With two or more states, existing exclusion behavior remains.
2. The exception applies even when the caller passes `allow_backoff_fallback=False`, because otherwise the single account's sticky/pinned path would still return no account. It does not clear the account's error state or shorten the backoff deadline; it makes one bounded selection from the already-eligible account.
3. Hard states are filtered before this condition, and a hard-blocked account never enters `in_error_backoff`. Request-level exclusions and concurrency remain outside this pure selector.
4. No `force` flag or new runtime reservation is introduced. This is the smallest safe liveness fix; broader per-replica recovery admission remains a follow-up with new tests and design.

## Risks / Trade-offs

- A persistent single-account failure will now receive one attempt per request instead of a local no-account response. Existing request deadlines, account caps and upstream failure handling bound that behavior; this is preferable to a self-inflicted outage for a one-account deployment.
- Multi-account pools do not gain the new behavior, so the original broad recovery design is not silently enabled.

## Rollout and rollback

Run focused selector tests plus the existing transient-retry suite. Rollback is a code revert; there is no persistent state or schema to migrate.
