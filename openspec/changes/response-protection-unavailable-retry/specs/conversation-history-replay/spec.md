## ADDED Requirements

### Requirement: Response protection unavailable replays anchored history

Before any output is forwarded, an HTTP SSE turn that still carries `previous_response_id` and fails with `internal_error` message `response protection is unavailable` MUST use the cached full-history replay when it moves to another account. The resend MUST omit `previous_response_id`, MUST include the cached history, and MUST consume the same one-resend budget as admission failover. When the cache cannot rebuild that history, the proxy MUST NOT move the turn. A history that contains a file id MUST NOT move. This replay MUST NOT add `internal_error` to the admission-failure set.

#### Scenario: Cached history moves once

- **GIVEN** the cache holds the completed turns behind a `previous_response_id`
- **AND** the history has no file id
- **WHEN** the owning account exhausts same-account retries on `response protection is unavailable` before any output
- **THEN** the proxy resends the turn once on a different account
- **AND** the resend contains the cached history and no `previous_response_id`

#### Scenario: A cache miss stays on the owner

- **GIVEN** the cache does not hold the turns behind a `previous_response_id`
- **WHEN** upstream returns `response protection is unavailable` before any output
- **THEN** the proxy does not send the turn to a different account
