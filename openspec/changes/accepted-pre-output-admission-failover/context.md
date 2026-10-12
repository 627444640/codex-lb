# Accepted pre-output admission failover

## Purpose

v1.24.4 (commit `65f56d0b`) is already in production. Six websocket requests were accepted and then failed with `server_error` or `server_is_overloaded` before any output. `output_delta_count` was 0, the client saw no model output, and `admission_failover_retried` was 0.

## Decision

`server_error` is not a capacity code, so the accepted capacity replay never classified it. Capacity codes were classified, but the failover note required `not accepted_lifecycle_replay`, so an accepted turn never recorded a switch.

An anchored turn cannot forward `previous_response_id` to another account. Cached full history is the only move. A cache miss does not switch a client-supplied anchor. Capacity misses that already replay on the owner, or that already swap a proxy-injected fresh body, keep that behavior.

File pins, hard sticky owners, and turn-state owners stay put. The original upstream is closed before the replacement request is sent. The request log stores the account that was left.

## Example

Account A sends `response.created` then `response.failed` / `server_error` for a follow-up whose history is cached. The proxy closes A's socket, drops `previous_response_id`, and sends the cached history once to account B. The completed request log has `admission_failover_retried=true` and `admission_failover_from_account_id=A`. A second admission failure on B is returned to the client.

## Failure modes

- Cache miss on a client anchor: the original error is forwarded and no other account is contacted.
- Tool-call or reasoning output already emitted: the error is forwarded.
- The history resend fails: that failure is forwarded. There is no third send.
- Both accounts failing together: the one failover cannot rescue the request. Production from 14:17:42 to 14:18:05 had both accounts erroring at the same time. The fix only helps when at least one healthy account is available. It does not drive the real-request error rate to 0%.
