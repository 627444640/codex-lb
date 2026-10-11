# One shared retry for admission failover and cached history

## Why

A `previous_response_id` that hits HTTP 500 or overload currently fails even when the conversation cache holds the full turn. Admission failover and history replay each keep their own retry counter, so one request can be resent twice. An HTTP SSE cut before the first token does not count toward the breaker, and the HTTP bridge does not participate.

## What Changes

- When a pre-output 500 or overload carries `previous_response_id` and the cache has the full history, drop the anchor and resend once on a healthy account. If the owner cannot be resolved, do not send the original id to another account.
- Admission failover and history replay share one pre-output resend on HTTP, WebSocket, and the HTTP bridge.
- An HTTP SSE stream that ends before the first token counts as an admission failure. One such failure increments the breaker once. Failures while the breaker is already open do not extend `open_until`.
- The accounts page shows breaker cards and the cache card. The request log shows whether the request switched accounts, was resent, or failed.

## Impact

Affected capabilities: account-admission-breaker, conversation-history-replay. Depends on those changes. No new settings and no schema migration.
