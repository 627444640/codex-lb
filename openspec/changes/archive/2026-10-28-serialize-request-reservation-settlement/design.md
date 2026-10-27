## Context

`_release_websocket_request_state_reservation` and terminal finalization both read the reservation before awaiting persistence. Detach/terminal/abort races can therefore enter persistence concurrently. The existing deterministic production-path simulation reproduces eight redundant-write schedules in its first latency profile.

## Goals / Non-Goals

Goals: one successful reservation write under concurrent healthy cleanup; preserve retry on unconfirmed failure and the settlement-before-health invariant.

Non-goals: changing quota accounting semantics, replacing database compare-and-set, redesigning every lifecycle path or serializing unrelated requests.

## Decisions

Each request state owns an internal async lock, excluded from dataclass construction/equality/repr. Release and terminal finalization hold it across the persistence call and the associated reservation-reference update. A concurrent path then observes the committed/handed-off state instead of submitting the original reservation again.

Failed or cancelled writes retain the reservation reference. The existing fallback/abort paths can acquire the lock and retry. Health and backoff draining stay outside the lock but follow confirmed settlement. Existing detached settlement-task ownership and database CAS remain in force.

## Risks / Trade-offs

The lock adds request-local waiting under races; it must not serialize independent requests. Cancellation while waiting must not cancel the active writer. Cancellation of an unconfirmed writer must release the lock while retaining its retryable reservation. Normal and failure paths are covered by explicit concurrency tests and the existing seeded production lifecycle schedules.

## Validation

The original canary fails with eight redundant-write schedules in its first profile when run with `--runxfail`. After the change, the related production-path simulation, HTTP-bridge unit tests and WebSocket integration slice pass: 1,268 passed, one Python-version skip. Five new tests cover shared ownership, failed/cancelled writers, cancelled waiters and independent requests. Ruff, changed-file typing, proxy architecture/cancellation/timing checks and strict OpenSpec validation pass. Existing intermittent Windows aiosqlite teardown warnings remain recorded; this change does not claim to fix those warnings.
