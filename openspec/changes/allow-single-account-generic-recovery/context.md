# Context

## Purpose and scope

This change is the narrow first stage of the generic-backoff recovery work. It keeps a one-account deployment live when the only blocker is generic transient backoff. It is not the full per-replica recovery-token design.

## Rationale

A one-account pool has no sibling to absorb a transient burst. Returning a local no-account response adds an outage on top of the upstream failure. The same liveness principle already applies to the admission breaker; this change extends it only to the separate generic backoff path.

## Constraints

Hard account states, quotas, rate limits, permissions, model eligibility and concurrency remain authoritative. The selector does not mutate the account's backoff timestamps. Multi-account behavior is unchanged. No new setting, schema, API or persistent state is introduced.

## Failure modes

- A genuinely broken single account will be attempted and return its real upstream error instead of a synthetic no-account response. Existing request deadlines and account caps constrain retries.
- A multi-account pool with one backoff account continues to rely on its sibling; the one-account exception is not a general force flag.
- A hard-blocked account is filtered before the backoff branch and cannot be revived by this rule.

## Example

A synthetic one-account state has `error_count=3` and `last_error_at=now`. The selector returns that account, leaving `error_count` and `last_error_at` unchanged. A second synthetic account with `status=quota_exceeded` is not returned.

## Publication

Only synthetic selector tests and sanitized OpenSpec artifacts are publication candidates. No production logs, databases, credentials or machine configuration are included. The existing release PR and unrelated local history remain untouched.

## Verification record

- Full `tests/unit/test_load_balancer.py` and `tests/integration/test_proxy_transient_retry.py`: 301 passed.
- Focused quota-bypass, single-account, multi-account and hard-state tests: 5 passed.
- Ruff/format and ty passed for the selector; strict OpenSpec validation passed for this change.
- Published as focused PR #22; no production request, merge or deployment was involved.
