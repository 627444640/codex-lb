# Design

## Usage `token_expired`

The global permanent-failure map remains authoritative for the OAuth token
endpoint. The usage endpoint must not use `token_expired` as a direct
reauthentication signal. A first usage 401 with that code follows the existing
forced `AuthManager.ensure_fresh` path and retries usage once with the returned
access token. If the retry still fails, it records the normal cooldown and
does not loop or mark reauthentication solely from the usage response.

## Stale usage status writes

Capture the encrypted refresh-token material used for the usage attempt before
awaiting the upstream call. Permanent usage errors are persisted through
`update_status_if_current`, conditioned on the account status, reason/reset
fields, deletion fence, and the captured refresh-token ciphertext. A compare
and-set miss reloads the account and returns without changing the local routing
overlay, session ownership, or in-memory status. A successful compare-and-set
retains the current cleanup and routing invalidation behavior.

## Model-discovery refresh retry

`RefreshError.retryable_same_contract` is the explicit replay-safety signal.
Only a non-permanent transport error with that flag set may rotate the shared
HTTP client and retry token refresh once in the current failover cycle. Body
read failures, timeouts after a request may have been accepted, claim
contention, token persistence conflicts, and permanent failures do not trigger
the retry. Model catalog GET transport recovery remains independently
retryable because that operation is idempotent.
