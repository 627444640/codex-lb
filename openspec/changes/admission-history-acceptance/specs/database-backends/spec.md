## ADDED Requirements

### Requirement: A bounded SQLite teardown drain is not repeated for the same wedge

When `close_db` reaches its bounded drain deadline with wedged teardown tasks still pending, it MUST record those tasks as already abandoned. A later `close_db` MUST NOT wait out that deadline again for the same still-pending tasks. A task that finishes after being abandoned, and any bookkeeping close it then schedules, MUST still be drained by a later `close_db` within one bounded deadline. The first `close_db` that observes a newly wedged task MUST still wait up to the deadline before abandoning it.

#### Scenario: A second shutdown does not rewait a task already abandoned

- **GIVEN** a wedged teardown task that does not finish
- **WHEN** `close_db` waits until the drain deadline and abandons it
- **AND** `close_db` runs again while that same task is still pending
- **THEN** the second call returns without waiting out the drain deadline again
- **AND** the task remains owned until it finishes

#### Scenario: A late bookkeeping close is still drained

- **GIVEN** a wedged teardown that was abandoned at the drain deadline
- **WHEN** that teardown finishes later and schedules its bookkeeping close
- **AND** `close_db` runs again
- **THEN** the bookkeeping close is drained within the bounded deadline
