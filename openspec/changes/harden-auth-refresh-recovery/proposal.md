# Harden authentication refresh recovery

## Problem

Usage refresh currently reuses the OAuth refresh-error classification table for
errors returned by the usage endpoint. That can turn an access-token-only
`token_expired` response into `reauth_required` without attempting the normal
refresh flow. Usage error status writes also do not carry a credential-version
compare-and-set guard, so a delayed response can invalidate a row that has
already been re-authenticated or rotated. Model discovery has a separate
transport-recovery path that retries a refresh after any transport failure,
including failures where the OAuth exchange may already have been accepted.

## Goal

Keep refresh-boundary permanent failures fail-closed while making usage
refresh distinguish access-token recovery, preventing stale usage responses
from overwriting newer credentials, and retrying an OAuth refresh only when the
transport failure is proven safe to replay.

## Scope

- Usage refresh classification and credential-version guarded status writes.
- Model-discovery OAuth refresh transport retry eligibility.
- Regression tests and OpenSpec requirements for these paths.

Production credentials, database data, deployment, and service restart are out
of scope for this change.
