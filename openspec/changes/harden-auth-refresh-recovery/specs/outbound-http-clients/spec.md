# Delta for outbound-http-clients

## Requirement: OAuth refresh transport recovery is replay-safe

The model registry refresh path MUST rotate the shared outbound HTTP client and
retry an OAuth refresh only when the `RefreshError` is non-permanent, has
`transport_error=True`, and has `retryable_same_contract=True`. It MUST NOT
retry or rotate for a transport error whose request may already have reached
the OAuth server, for refresh claim contention, persistence/status CAS
conflicts, or any permanent refresh error. The existing idempotent model
catalog GET recovery remains allowed independently.

#### Scenario: Pre-dispatch connector failure is retried

- **WHEN** token refresh fails before a request can be sent
- **AND** the error is marked `retryable_same_contract=True`
- **THEN** the shared client is rotated and the refresh is retried at most once

#### Scenario: Ambiguous refresh failure is not replayed

- **WHEN** token refresh fails with `transport_error=True` but
  `retryable_same_contract=False`
- **THEN** the shared client is not rotated for this recovery
- **AND** the old refresh token is not sent a second time by model discovery
- **AND** the error follows the existing failover handling
