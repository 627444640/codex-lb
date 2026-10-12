# Account admission breaker

## Purpose

Production traffic kept landing on an account that upstream was already rejecting with `server_error` and `server_is_overloaded`. Warm-session successes cleared `error_count`, so the existing health penalty never held the account out. This change stops new assignment during that burst and hides a single pre-output failure from the client when another healthy account can take it.

## Decisions

- The transport circuit breaker stays disabled. It counts unknown exceptions, including client disconnects, and selection only notices it when every account is open.
- Overload backoff stays a preference reorder. It does not count `server_error` or an authored close before output, and it falls back onto the sick account.
- Defaults are on, with threshold 3, window 60 seconds, and open interval 300 seconds. A two-account pool needs those knobs because burst length is not the same everywhere. They are internal tuning and are not added to `.env.example`.
- A success while the breaker is open does not close it. Only the half-open probe success recovers the account.
- One cross-account retry, then stop. HTTP 500 still spends the existing three same-account transient attempts before that move, so one blip stays on the account that already accepted the request. Other qualifying failures do not gain an extra same-account loop.
- `previous_response_id` owned by the tripped account, a file pin, and `single_account` routing are not switched. History replay is a later change. A verified fresh body that the existing websocket path already treats as safe to move may still move.

## Failure modes

- Each replica trips on its own observations. A second replica can still send new work until it sees the same burst.
- If every account is open, new requests fail with `account_admission_breaker_open` until a probe is allowed.
- A frame-less close (no close code, or 1006) stays account-neutral and does not trip the breaker.
- Continuity-pinned requests fail on the owner instead of moving. The client sees that error.

## Example

Account A returns `server_error` at t=0s, t=10s, and t=20s. The third failure opens the breaker until t=320s. A new request during that window goes to account B. At t=321s one probe may use A. If that probe returns `server_error` before any output, the breaker opens for another 300 seconds. If the probe completes, A returns to normal assignment.

A request whose `previous_response_id` is owned by A is still sent to A. If A fails before output, the proxy does not switch accounts.
