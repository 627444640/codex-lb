## ADDED Requirements

### Requirement: Concurrent selection cache misses coalesce per scope

With selection caching enabled, concurrent requests for the same valid routing-scope cache key SHALL reuse one successful snapshot load while that snapshot remains fresh. Different scopes SHALL remain independent. Cancellation or failure of a loader SHALL permit a waiting request to retry, and coordination state SHALL be released after the last participant exits.

#### Scenario: Same-scope cold burst

- **WHEN** several requests miss the same fresh-cache scope concurrently
- **THEN** only the load owner reads its account and usage snapshot
- **AND** waiters reuse detached copies without crossing account scopes

#### Scenario: Loader is cancelled

- **WHEN** the owning snapshot load is cancelled before storing data
- **THEN** a waiting request can become the loader
- **AND** cancellation of a waiter cannot cancel the active loader

#### Scenario: Different scopes load concurrently

- **WHEN** requests miss different routing scopes
- **THEN** a blocked load for one scope does not block the other scope

#### Scenario: Invalidation races an in-flight load

- **WHEN** invalidation advances the generation during a load
- **THEN** the stale load does not repopulate the cache
- **AND** later owners load current state using the existing generation checks
