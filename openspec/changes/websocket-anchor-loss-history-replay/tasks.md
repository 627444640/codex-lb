## 1. Implementation

- [x] 1.1 Add a predicate for a direct WebSocket `previous_response_not_found` terminal that may resend cached history: anchored, no retry-safe fresh body, single pending request, no replay spent, no model output, and either pre-created or accepted with only the lifecycle prelude exposed.
- [x] 1.2 Stage the history replay before the stale-anchor fail-closed is recorded, for both shapes; keep the account unless the admission breaker blocks it.
- [x] 1.3 Leave the fail-closed rewrite unchanged on a cache miss or when the predicate refuses.
- [x] 1.4 Treat a suppressed replay `response.in_progress` like the suppressed `response.created` in the replay sequence check.

## 2. Regression coverage

- [x] 2.1 Cache hit after `response.created`: the turn is resent once without `previous_response_id`, and no `continuity_fail_closed` is logged.
- [x] 2.2 Cache hit before `response.created`: the replay is staged without a `continuity_fail_closed`.
- [x] 2.3 Cache miss: the existing fail-closed terminal and diagnostics are returned.
- [x] 2.4 Any model output before the terminal: no replay.
- [x] 2.5 One replay per request: a spent budget or a second anchor loss fails closed.
- [x] 2.6 Product path: `/backend-api/codex/responses` recovers an accepted anchor loss from the cache, with one `response.created` and an advancing sequence downstream.
