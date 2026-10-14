## Why

On the HTTP responses bridge, a soft preferred account whose admission breaker is open is still selected. With one other account in the pool that account was not healthy, so selection returned HTTP 503 `account_admission_breaker_open` ("Admission breaker blocked"). Two healthy accounts are active now, and the same soft preference still does not move. Follow-ups on that preference carry `previous_response_id`, which is account-scoped and must not be forwarded to the replacement account.

## What Changes

- A soft preferred account (HTTP bridge key strength is not `hard`, owner check is not applied, not file-pinned, not `single_account`) whose admission breaker is open, or half-open with the probe already in flight, is left out of selection. Another healthy account is chosen, and the request log records the admission failover and `account_admission_breaker_open`.
- A first turn with no `previous_response_id` moves directly.
- A follow-up moves only by replaying the cached full history with `previous_response_id` removed and `history_replay_reason=owner_unavailable`. If the cache does not hold the chain, the bridge returns HTTP 503 `account_admission_breaker_open` and does not open another account.
- Hard bindings do not move. A hard Codex session owner that is not an ownership pin still returns that 503. An ownership pin stays on its account. A disabled breaker does not change selection.

## Capabilities

### Modified Capabilities

- `account-admission-breaker`: soft preferred HTTP bridge selection fails over while the owner is admission-blocked.
- `conversation-history-replay`: that failover resends cached history without `previous_response_id`, or refuses to forward when the cache misses.

## Impact

HTTP bridge dispatch (`app/modules/proxy/_service/http_bridge/streaming.py`) and preferred-account selection (`app/modules/proxy/service.py`). No new setting, no schema change, no dashboard change.
