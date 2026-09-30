# Delta for usage-refresh-policy

## Requirement: Usage access-token expiry uses the refresh path

The usage endpoint MUST NOT classify `token_expired` as a refresh-token
permanent failure. On the first usage HTTP 401 carrying `token_expired`, the
updater MUST attempt one forced `AuthManager.ensure_fresh` and retry the usage
request with the returned access token. If that retry also fails, the updater
MUST apply its normal authentication cooldown and MUST NOT mark
`reauth_required` solely from the usage response or perform an unbounded retry.

The OAuth token endpoint MUST continue to classify `token_expired` as a
permanent refresh failure.

#### Scenario: Usage token expiry refreshes the access token

- **WHEN** the first usage request returns HTTP 401 with code `token_expired`
- **THEN** the updater calls forced token refresh once
- **AND** retries usage with the refreshed access token
- **AND** it does not directly write `reauth_required` from the first usage error

#### Scenario: Repeated usage token expiry is bounded

- **WHEN** the retry after forced refresh also returns HTTP 401 with code `token_expired`
- **THEN** the updater records the normal usage authentication cooldown
- **AND** it does not call forced refresh again in the same refresh operation
- **AND** it does not write `reauth_required` from that usage response

## Requirement: Permanent usage status writes are credential-version guarded

Before a usage request, the updater MUST capture the encrypted refresh-token
material belonging to the access token used by that request. A permanent usage
status transition MUST use `update_status_if_current` conditioned on that
captured refresh-token material and the account status/reason/reset snapshot.
When the compare-and-set misses, the updater MUST reload the account and MUST
NOT change local routing availability, sticky/bridge sessions, or the
in-memory status from the stale response.

#### Scenario: Delayed usage error cannot invalidate a re-authenticated account

- **GIVEN** a usage request was sent with an older credential version
- **AND** the account is re-authenticated before the usage request returns
- **WHEN** the old request returns a permanent usage authentication error
- **THEN** the guarded status write misses
- **AND** the repaired account remains selectable with its sessions intact

#### Scenario: Current permanent usage failure is still isolated

- **GIVEN** the account still has the credential version used by the usage request
- **WHEN** the usage request returns a clear permanent account/session error
- **THEN** the guarded status write succeeds
- **AND** the account is marked with the existing `reauth_required` or
  deactivated status and routing cleanup runs once
