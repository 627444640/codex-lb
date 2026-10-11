# Stop assigning new work to an account that upstream is rejecting

## Why

Seven days of production request logs on v1.24.3 showed 8519 requests and 579 errors (6.8%). Almost all `server_error` and `server_is_overloaded` bursts sat on one of two accounts, and selection kept using that account. Many `stream_incomplete` rows were an authored websocket close before any output.

## What Changes

- Open a per-account admission breaker after 3 qualifying upstream failures in a row, or 3 inside 60 seconds. Hold the account out of new assignment for 300 seconds, then allow one half-open probe.
- Before any output is forwarded, retry an admission failure once on a different healthy account after a short jitter. After output starts, surface the failure and log it as interrupted mid-stream.
- Do not move a request that is pinned by `previous_response_id`, a file, or single-account routing.
- Record the failover on the request log and expose `GET /api/accounts/admission-breakers`.

## Impact

Affected capability: account-admission-breaker. The transport-level circuit breaker stays off. Overload backoff remains a soft preference. Breaker phase is replica-local.
