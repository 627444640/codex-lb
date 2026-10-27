## ADDED Requirements

### Requirement: Concurrent transport cleanup shares reservation ownership

Concurrent detach, terminal and abort paths for one proxy request SHALL serialize access to its API-key reservation. After a successful settlement, another cleanup path SHALL NOT submit the same live reservation for a redundant write. A failed or cancelled unconfirmed write SHALL retain retryable ownership. Account-health writes SHALL remain ordered after confirmed settlement.

#### Scenario: Detach races terminal cleanup

- **WHEN** multiple terminal cleanup paths observe the same request while its settlement is in flight
- **THEN** at most one successful reservation write is submitted for that healthy cleanup
- **AND** later paths observe the settled state

#### Scenario: Unconfirmed release fails or is cancelled

- **WHEN** a reservation write fails or is cancelled before confirmation
- **THEN** the reservation remains available to the existing recovery owner
- **AND** deferred account-health mutations remain unapplied until settlement is confirmed

#### Scenario: A waiting cleanup task is cancelled

- **WHEN** a cleanup task is cancelled while another path owns settlement
- **THEN** the active settlement is not cancelled by the waiter
- **AND** unrelated requests can settle independently
