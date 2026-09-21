## ADDED Requirements

### Requirement: SQLite credential snapshots have an independently checked offline restore

A local database/key rehearsal MUST read the source SQLite database in read-only
mode and create a consistent backup through the SQLite backup API. It MUST keep
the matching encryption key, reject a key change during the snapshot, restrict
snapshot directories to their owner, and refuse to overwrite an existing run.
The archive MUST be restored into a separate directory and independently checked
for file integrity, SQLite integrity and decryptability of every stored account
credential. No plaintext credential, device identifier or credential value MUST
be included in the public result. The rehearsal MUST NOT start the application,
refresh an account, call a model, or change the source database or active key.

#### Scenario: A database and matching key survive archive restoration
- **GIVEN** an existing SQLite database and matching encryption key
- **WHEN** the private snapshot is archived and restored to a new directory
- **THEN** every expected file checksum and SQLite integrity check passes
- **AND** all account credential fields decrypt without exposing their contents
- **AND** source data and active services are left unchanged

#### Scenario: An invalid key or changed key blocks a valid-backup result
- **GIVEN** the key does not decrypt the snapshot, or changes while it is captured
- **WHEN** the snapshot is verified
- **THEN** the command fails without reporting a verified backup
- **AND** it never substitutes a newly generated encryption key

### Requirement: Local SQLite writer waits remain observable without exposing credentials

For file-backed SQLite, the process-local serialized writer section MUST report
queue acquisition waits of at least 100 ms, including cancelled acquisitions.
The log MUST include only duration, outcome and queue depth; no SQL parameters,
account identities or credentials. Instrumentation MUST preserve cancellation
and lock ownership. These samples MUST NOT be represented as all database wait
time, a cross-process lock measurement or a complete background queue metric.

#### Scenario: A queued writer acquires or is cancelled
- **GIVEN** another task holds the local SQLite writer section
- **WHEN** the queued task waits at least the reporting threshold and either acquires or is cancelled
- **THEN** a structured duration and outcome are recorded
- **AND** cancellation leaves no abandoned waiter or stolen writer ownership
