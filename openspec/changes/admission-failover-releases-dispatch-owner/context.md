# Admission failover releases the dispatch owner

## Purpose

v1.24.5 (`0e0e5ffe`) is in production. A request could spend its one pre-output admission failover and still never reach a second account. The body was account-bound, the failed account was both excluded and required, and selection returned `preferred_account_unavailable`.

## Production evidence

- An HTTP streaming request of about 29 MB skipped the HTTP bridge and was sent to account `cc0d7baf`.
- Upstream sent `response.created` and then `server_is_overloaded` before any output.
- The `_RetryableStreamError` handler in `streaming/retry.py` recorded the failure, set `admission_failover_used=True` and added `cc0d7baf` to `excluded_account_ids`.
- `payload_replay_required_account_id` was still `cc0d7baf`. It is set at first dispatch, and only the history-replay branch cleared it.
- The next selection sent `preferred_account_id=cc0d7baf` with `fallback_on_preferred_account_unavailable=False`. It returned `preferred_account_unavailable`, and the healthy account `d2aad9f3` was not tried.
- The terminal branch emitted `server_is_overloaded` and wrote a second row with `account_id=NULL` and no failover flags.

## Decisions

- An admission rejection before any model output means upstream never started the response. The dispatch account holds no state for this turn, so the failed body can move.
- The body may still carry retained encrypted reasoning or item ids from earlier turns. Conversation-history replay already moves the same items across accounts on an admission failure, so this change uses the same boundary. The account-neutral fresh-replay predicate is too strict for this case: it rejects every encrypted reasoning item, and Codex sends one on almost every follow-up.
- The binding stays when the body names something only the dispatch account can resolve: `previous_response_id`, `conversation`, `prompt`, a file, container or vector-store id, an `item_reference`, or a non-HTTP file or image URL. Moving those would turn the overload into an object-not-found error on B.
- A previous-response or turn-state owner (`require_preferred_account`), a file pin, and `single_account` routing keep the binding. A hard sticky Codex-session owner is enforced by account selection, which returns `hard_affinity_saturated` instead of moving the request.
- Only the admission codes release the binding. A 502, a pre-output `stream_incomplete`, or a 429 on a bound body still fails closed, as before.
- The one-failover budget is unchanged. Releasing the binding only lets the failover that was already decided reach another account.

## Request log

Streaming keeps each attempt open across many SSE chunks. The keepalive wrapper and the first-chunk probe pull chunks in separate tasks, so a failover mark set in one chunk's task is gone by the time the next attempt writes its row. The retry loop now passes the marks it has seen to each attempt explicitly.

- The failed attempt's row records the error on account A with no failover flag.
- The next attempt's row records `admission_failover_retried=true` and `admission_failover_from_account_id=A`. One failover gives one flagged row.
- When retry selection ends the request and the failed attempt already wrote its row, the terminal branch does not write another. If no attempt wrote a row for that error (for example a refresh failure before dispatch), the terminal row records the failed account and the marks.

The dashboard and the request-log list read these columns per row. The failover count is now the number of failovers, not zero, and the duplicate accountless error rows are gone.

## WebSocket and HTTP bridge

Neither transport reaches this dead end. The direct WebSocket path excludes an account on an admission failure only when `_websocket_admission_may_switch_account` allows it. That check fails when `replay_required_account_id` is set or when the affinity may resolve a hard owner. A bound request reconnects to its owner or surfaces the error. A history replay clears the binding before it excludes. The HTTP bridge keeps an account-bound replay on the same account through `require_same_account`. No account is both excluded and required, so no change is made there.

## Failure modes

- No other healthy account: the overload is returned to the client with one row on A.
- B rejects the retained body, for example because it cannot decrypt reasoning from A: B's error is returned. There is no third send.
- B is overloaded too: B's failure is returned to the client, and B's row carries the failover flags.
- Both accounts failing together cannot be rescued by one failover. The fix only helps when a healthy account exists.

## Example

Account A accepts a turn whose input carries an encrypted reasoning item, then fails with `server_is_overloaded` before any output. The proxy closes A's stream, releases the binding, excludes A, and sends the same body once to account B. B completes the turn. The request log has A's error row with no flag and B's success row with `admission_failover_retried=true` and `admission_failover_from_account_id=A`.
