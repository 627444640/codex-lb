## 1. Selection

- [x] 1.1 When a preferred account is only soft and its admission breaker blocks a new assignment, exclude it and select another healthy account. Log `admission_failover` with reason `account_admission_breaker_open`.
- [x] 1.2 When no other healthy account remains, return HTTP 503 `account_admission_breaker_open` / "No available accounts".
- [x] 1.3 Leave ownership pins, hard Codex sticky owners, `single_account`, and a disabled breaker on their current path.

## 2. HTTP bridge follow-up

- [x] 2.1 A soft follow-up with cached history strips `previous_response_id`, replays the full chain, and records `history_replay_reason=owner_unavailable` before session creation.
- [x] 2.2 A soft follow-up with no cached chain returns HTTP 503 and does not create a session on another account.
- [x] 2.3 A first turn with no `previous_response_id` falls back directly.
- [x] 2.4 A pre-output failure on the fallback account after that replay is forwarded. The shared retry is not spent again, and a third account is not selected.

## 3. Tests and release

- [x] 3.1 Cover soft fallback, no-other-account 503, hard unchanged, breaker disabled, cached follow-up replay, and cache-miss 503.
- [x] 3.2 Bump the package version to 1.24.8.
