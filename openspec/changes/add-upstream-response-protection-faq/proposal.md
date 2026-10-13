# Add upstream response-protection FAQ guidance

## Why

The gateway has a recurring `internal_error` response with the message
`response protection is unavailable`. Existing FAQ guidance covers generic
`server_error`, but does not explain the verified routing evidence, the
account-pool amplification, or the limits of the current diagnosis.

## What Changes

- Add a published FAQ guide for the exact response-protection error signature.
- Describe the verified upstream-stream failure boundary and safe operator
  checks without exposing request IDs, account identifiers, credentials or
  raw request content.
- Version the FAQ seed import so an existing monitor adds the guide while
  preserving administrator edits, withdrawals and deletions.

## Impact

This changes only the independent status monitor's published FAQ content and
seed-upgrade behavior. It does not change gateway routing, retries, account
health, model generation, database schemas or alerting.
