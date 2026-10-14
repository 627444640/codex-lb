## Purpose

Stop sending a soft-preferred HTTP bridge turn to an account whose admission breaker will not take a new assignment, without handing that account's `previous_response_id` to a different account.

## Decisions

Soft versus hard is decided before selection. Soft means the preferred account is not an ownership constraint: HTTP bridge key strength is not `hard`, owner check is not applied (`_http_bridge_owner_check_required`), the turn is not file-pinned, routing is not `single_account`, and `fallback_on_preferred_account_unavailable` is still true. `previous_response_id` alone does not make the preference hard.

The breaker check is `account_admission_blocks`: phase `open`, or `half_open` with the probe already in flight. A half-open account with a free probe stays the preferred account so it can take that probe. A disabled breaker reports not blocked, so selection is unchanged.

A follow-up uses the same history planner as the 1.24.7 HTTP `previous_response_not_found` replay (`plan_replay`): drop `previous_response_id`, prepend the cached chain, refuse the move when the chain or the turn contains a file id. The reason is `owner_unavailable`, the same reason the bridge already uses when the breaker blocks the owner before an upstream admission error code. The failover also calls `note_admission_failover`, which spends the one shared retry.

A cache miss returns the existing 503 `account_admission_breaker_open` / "No available accounts" before `_get_or_create_http_bridge_session`. The original id is not sent.

Hard Codex sticky selection that is not an ownership pin still hits the post-check log "Admission breaker blocked new assignment" and returns that 503. An ownership pin (`required_account_is_ownership_constraint`, including key strength `hard`, `require_same_account`, and a file pin) still skips the breaker and stays on the pinned account.

## Constraints

No new `CODEX_LB_*` setting. The replay and the failover share one retry. Re-preparing the bridge request would open a second API-key reservation, so the staged body is written onto the existing request state and `text_data`.

## Failure modes

Cache miss, or a chain that contains a file id: HTTP 503, no second account, anchor not forwarded. No other healthy account: the same 503. Breaker disabled, or half-open with a free probe: the preferred account is still selected. Hard ownership pin: still that account. Hard Codex owner without an ownership pin: still 503, not the sibling.

## Example

Account A is the soft preferred owner of `resp-1` and its breaker is open. Account B is healthy. A follow-up `previous_response_id=resp-1` with input "more" is resent to B with the cached turn "kept" plus "more", and no `previous_response_id`. The request log stores `history_replay_reason=owner_unavailable` and the failover from A. The same follow-up with an empty cache returns HTTP 503 and does not call account B.
