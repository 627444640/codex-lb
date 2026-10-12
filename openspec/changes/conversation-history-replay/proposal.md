# Replay a lost turn from cached conversation history

## Why

Of resume failures in the last 7 days, 8 were `previous_response_not_found` (upstream lost the response and the proxy had nothing to replay), 110 were `stream_incomplete` on the same account (99 before the first token), and 28 were `previous_response_owner_unavailable` while the owner was in its failure window. Cross-account resume was 1 of 145. The admission breaker holds that owner out of new work, and without a local copy of the conversation the pinned turn cannot move.

## What Changes

- Cache completed turns for in-flight conversations in a separate SQLite file. On `previous_response_not_found` or a pre-first-token `stream_incomplete`, resend the turn once on the same account with the cached history and no `previous_response_id`. When that owner is admission-open or otherwise unavailable, resend the same history on a healthy account.
- Keep the resend to one attempt, before any output reaches the client, after a short jitter. The close still counts toward the admission breaker.
- Cap the file at 1 GiB, each conversation at 32 MiB, and idle entries at 30 minutes. Evict by LRU, reclaim space with incremental vacuum, and disable the cache when free disk is under 512 MiB.
- Record the replay reason and extra input tokens on the request log. Expose occupancy stats, not conversation text, at `GET /api/accounts/conversation-history-cache`.

## Impact

Affected capabilities: conversation-history-replay, account-admission-breaker. Depends on the admission breaker. The cache file is not `store.db` and has no Alembic revision of its own. Request logs gain two nullable columns.
