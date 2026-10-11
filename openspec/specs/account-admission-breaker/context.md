# Account admission breaker

## Purpose

Keep a new request off an account that upstream is rejecting in a burst, and hide one pre-output failure when another account can take the request.

## Decisions

The transport circuit breaker stays off. It treats unknown exceptions as server errors and does not remove a single sick account from selection. Overload backoff only deprioritizes `server_is_overloaded` and falls back onto that account.

Defaults are enabled, threshold 3, window 60 seconds, open 300 seconds. Threshold and timing stay configurable because a two-account pool and the length of an upstream burst are not the same on every install. Those settings are internal; they are not listed in `.env.example`.

A success while the breaker is open does not close it. Warm sessions were clearing the generic error counter and hiding the sick account. Only the half-open probe success recovers the account.

One cross-account retry is the cap. The same account is not retried for these failures, so an upstream outage is not multiplied by the old three same-account attempts.

A `previous_response_id` owned by the failed account, a file pin, and `single_account` routing stay on that owner. Replaying history onto another account is a later change.

## Constraints

Breaker phase lives in the replica's routing runtime. It is not written to the database. Error rates on the status API are computed from shared request logs.

## Failure modes

A second replica can still assign new work until it observes the same burst. If every eligible account is open, selection fails with `account_admission_breaker_open` until a probe is allowed. Close code 1006 and a missing close code stay account-neutral. Continuity-pinned requests fail on the owner instead of moving.

## Example

Account A returns `server_error` three times inside a minute. The breaker stays open for five minutes and new requests use account B. When the five minutes elapse, one probe may use A. Probe success closes the breaker. Probe failure opens it for another five minutes.

A turn that still names a `previous_response_id` stored for A is sent to A even while the breaker is open. If A then fails before output, the proxy does not switch accounts.
