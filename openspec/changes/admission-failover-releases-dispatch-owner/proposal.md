## Why

Production on v1.24.5 (`0e0e5ffe`): an HTTP streaming request on account `cc0d7baf` received `response.created` and then `server_is_overloaded` before any output. The body was about 29 MB, so it skipped the HTTP bridge. The admission failover recorded the failure, set `admission_failover_used` and excluded `cc0d7baf`. The body was not account-neutral, though, so the first dispatch had bound it to `cc0d7baf` through `payload_replay_required_account_id`. Only the history-replay branch cleared that binding. The retry therefore required the excluded account, selection returned `preferred_account_unavailable`, and the healthy account `d2aad9f3` was never tried.

The terminal path then wrote a second request-log row with `account_id=NULL` and no failover flags. Stats showed `admission_failover_retried=0` and duplicate rows. The flags were also missing on rows written after a successful failover: streamed attempts can finish in a different task from the one that recorded the failover, and the context variable does not follow.

## What Changes

- An HTTP streaming admission rejection (`server_error`, `server_is_overloaded`, `overloaded_error`) that spends the one pre-output failover releases the dispatch-owner binding before reselection. Sticky reallocation is requested at the same time.
- The binding is kept when a real continuity owner applies: a `previous_response_id` owner, a turn-state owner, a file pin, `single_account` routing, or a body that names upstream objects only that account can resolve. A hard sticky owner is still enforced by account selection.
- Each attempt's request-log row records the failover and history-replay marks that were known when the attempt started. The marks are passed explicitly, not read from task context.
- When retry selection ends the request and the failed attempt already wrote its row, no extra terminal row is written. When a terminal row is still needed, it records the account that failed and the failover marks.
- WebSocket and HTTP bridge: no code change. They never exclude a bound owner on an admission failure, so they cannot reach the same dead end.

## Capabilities

### Modified Capabilities

- `account-admission-breaker`: the pre-output failover can move a dispatch-bound body, and the request log has one flagged row per failover.
- `responses-api-compat`: the dispatch-owner binding has an exception for pre-output admission rejections.

## Impact

HTTP streaming retry (`app/modules/proxy/_service/streaming/retry.py`), request-log writes, and the replay-safety predicate. No schema change, no new setting, no version bump in this change.
