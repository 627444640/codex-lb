## ADDED Requirements

### Requirement: SQLite history caching has a bounded working set

The SQLite dashboard history cache SHALL advance its retained `since` boundary to the current query window, expire entries after 30 seconds, retain at most 32 account/window sets and at most 100,000 snapshots across those entries. A query exceeding the snapshot budget SHALL return all matching history without retaining it. Eviction and expiration SHALL NOT truncate query results or delay detection of corrections or deletions to retained history. Global cache synchronization SHALL NOT span SQLite queries or content hashing. Explicit invalidation SHALL prevent an in-flight read from repopulating the cache with its earlier snapshot.

#### Scenario: Dashboard projection window moves forward
- **WHEN** successive projection requests move the history cutoff forward
- **THEN** cached snapshots older than the current cutoff SHALL be discarded
- **AND** subsequent content verification SHALL scan only the current window
- **AND** requesting a wider window again SHALL reload the missing history

#### Scenario: Expiry and capacity do not change history results
- **WHEN** a cache entry expires or the entry or snapshot budget is exceeded
- **THEN** a query SHALL return the same complete history as an uncached query
- **AND** the cache SHALL stay within its entry and snapshot budgets

#### Scenario: Retention invalidation overlaps a slow history read
- **GIVEN** a read has captured a database snapshot before retention or account mutation clears the cache
- **WHEN** that read completes after invalidation
- **THEN** it SHALL NOT publish its earlier snapshot into the cache
- **AND** invalidation and queries for other account/window sets SHALL not wait for that read's SQLite queries or hashing

#### Scenario: Concurrent modification cannot mix verification and append snapshots
- **WHEN** a database writer corrects existing rows while a cached history query is running
- **THEN** content verification and append loading SHALL use one database read snapshot
- **AND** the next query SHALL observe the committed correction
