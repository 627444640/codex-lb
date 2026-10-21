# Context

## Purpose and scope

This is the first focused delivery of the reviewed recovery-reliability plan, tracked by issues #15 and #16 in the fork. It covers bridge failure attribution and truthful admission errors, not a wholesale retry redesign.

## Rationale

A bridge refusal and an upstream execution failure are different facts. A future cooldown can carry a real wait duration, while a half-open probe can be occupied after the cooldown is already zero. Calling both an upstream timeout obscures the evidence and can accidentally engage the wrong recovery consumer.

## Constraints

The existing circuit counts stream_incomplete, clean_close and stream_idle_timeout under its documented eligibility rules. Its thresholds, persisted state, dead-anchor cleanup, operation fence and generation claim remain in place. No shared resend budget or account ownership constraint is relaxed. No new settings or database schema are introduced.

## Synthetic example

A synthetic bridge key has two previous failures, an expired cooldown and an active half-open probe. A second ordinary request must remain refused, but must not invent a one-second cooldown. A proof-gated request and an operation-fenced request retain their existing, different allowance rules. This example contains no production identity or request payload.

## Failure modes

- A public error-code change can accidentally trigger another upstream send if inserted into an ambiguous-transport allowlist.
- Returning an object where callers expect a boolean can invert refusal semantics.
- A cleanup label applied to an entire session can erase a sibling's UNKNOWN or ACKNOWLEDGED evidence.
- Shortening constants does not remove older durable deadlines; this change intentionally does not shorten either.

## Privacy and publication

Only reviewed source, synthetic tests and these sanitized artifacts are publication candidates. Production logs, databases, backups, credential/environment files, conversation archives, machine configuration and raw tool output are excluded. A push must also check newly published ancestor commits, not only the final diff. The existing release-line PR is not silently updated by this work.

## Verification record

- Baseline bridge subset: 43 existing tests passed (`retry_circuit`, generation claims, poison cleanup and server-anchored cooldown guards).
- New synthetic gate module: 18 tests passed, including half-open-zero-duration, allowance asymmetry, one-probe concurrency, durable restoration and lookup failure.
- Durable CAS and SSE retry-hint nodeids: 4 tests passed.
- Ruff check/format and ty passed for the changed source and test files; strict OpenSpec validation passed for this change.
- Typed gate consumers now return `bridge_session_cooldown` only with a future deadline; half-open occupancy and generation-claim failure return `upstream_unavailable` without a fabricated delay.
- Focused submit, startup HTTP, SSE retry-hint and generation-claim tests passed; existing sibling/per-attempt attribution tests passed unchanged.
- The public error code is not added to ambiguous-upstream recovery allowlists. Raw local output is intentionally not published.
