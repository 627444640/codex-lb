## ADDED Requirements

### Requirement: Account selection cache residency is bounded

The proxy SHALL retain at most 256 cached account-selection snapshots per process by default. Expired snapshots SHALL be reclaimed on access and before admitting new snapshots. Disabling caching SHALL retain no snapshots. Eviction SHALL cause a normal cache miss without changing account eligibility, scope, affinity, quota checks or lease settlement.

#### Scenario: Distinct routing scopes exceed cache capacity

- **WHEN** requests populate more distinct model, tier or account scopes than the cache capacity
- **THEN** resident snapshot count stays within capacity
- **AND** a request for an evicted scope reloads its own eligible accounts
- **AND** it cannot reuse another scope's snapshot

#### Scenario: Expired snapshots are reclaimed

- **WHEN** an expired snapshot is requested or another snapshot is stored
- **THEN** the expired data is not returned
- **AND** obsolete resident entries are removed during the operation

#### Scenario: Cache is disabled

- **WHEN** the account-selection cache has a zero time-to-live
- **THEN** snapshot stores retain no data and all reads miss

### Requirement: Bounded cache preserves invalidation fencing

The proxy SHALL reject a snapshot store whose load generation predates an invalidation, including when capacity eviction or expiry reclamation has occurred. Capacity eviction SHALL NOT emit a cross-replica invalidation or change the invalidation generation.

#### Scenario: Invalidation races a database snapshot load

- **WHEN** a load begins before cache invalidation and completes after it
- **THEN** that load cannot repopulate the cache
- **AND** a subsequent request reloads the current routing state

#### Scenario: Capacity eviction is local

- **WHEN** inserting a snapshot evicts an older snapshot
- **THEN** peers receive no invalidation event solely because of the eviction
- **AND** the local generation remains unchanged
