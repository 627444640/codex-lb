## ADDED Requirements

### Requirement: macOS maintenance waits for complete service shutdown

The macOS management CLI MUST bound the entire shutdown operation, including LaunchAgent removal. It MUST confirm completion of LaunchAgent removal, absence of the observed job process groups, and closure of the service listener before backup or restore may modify service files. Permission errors and incomplete shutdowns MUST fail closed. A retry MUST NOT lose the evidence of an earlier incomplete shutdown merely because the job has already been unloaded.

#### Scenario: Listener closes before the final write

- **WHEN** a stopping service closes its listener and then completes an outstanding write
- **THEN** the management command waits for complete process-group exit before reporting the service stopped
- **AND** backup and restore cannot begin while that write remains possible

#### Scenario: LaunchAgent removal exceeds its deadline

- **WHEN** LaunchAgent removal or process-group exit cannot be confirmed within the shutdown deadline
- **THEN** the command reports failure instead of hanging indefinitely
- **AND** retrying cannot treat a closed listener alone as proof of shutdown

### Requirement: macOS restore preserves damaged current state independently

After validating the requested backup, the macOS restore CLI MUST be able to restore it when the current database is missing or damaged. Before replacing service files it MUST stop the services and publish a checksummed raw snapshot of the current files. Raw snapshots MUST be identified as unverified recovery material, excluded from normal healthy-backup retention, and rejected by normal backup verification and restore. Failure to preserve the raw snapshot MUST prevent replacement and attempt to recover the prior service set.

#### Scenario: The current database is damaged or absent

- **WHEN** the operator restores a valid backup over a damaged or missing current database
- **THEN** restoration proceeds without requiring the current database to pass integrity checks
- **AND** a separate raw snapshot preserves the damaged bytes or original absence

#### Scenario: Saving the original files fails

- **WHEN** raw snapshot creation or publication fails
- **THEN** no replacement directories or versions are installed
- **AND** the command attempts to restore the prior service set

#### Scenario: A raw snapshot is passed as a normal backup

- **WHEN** the operator runs normal backup verification or restore against a raw recovery snapshot
- **THEN** the command rejects it as unverified recovery material

### Requirement: macOS supervisors drain final logs within a deadline

After observing child exit, the macOS supervisor MUST continue reading buffered stdout until EOF or a fixed drain deadline. It MUST retain the child's exit status, redaction, and oversized-line limits. If a descendant keeps the pipe open beyond the deadline, the supervisor MUST report incomplete draining and exit instead of waiting indefinitely.

#### Scenario: A child exits immediately after burst output

- **WHEN** a child writes multiple read-buffer lengths of short log lines and a final diagnostic before exiting
- **THEN** the supervisor records every complete line and the final diagnostic before reporting exit
- **AND** a final line without a newline is retained

#### Scenario: A descendant holds stdout open

- **WHEN** the child exits but a descendant prevents stdout EOF
- **THEN** the supervisor exits within its drain deadline and emits an incomplete-drain warning
- **AND** the original child exit status is preserved

### Requirement: Public macOS tooling excludes private deployment material

The repository SHALL publish reusable macOS tooling under `deploy/macos/` with
synthetic examples and isolated tests. It MUST NOT require the author's home
path, hostname, credentials or runtime files. Actual deployment configuration,
certificates, database files, logs, backups and private audit reports MUST stay
outside the published source and its Git history. The local private deployment
snapshot and withdrawn history MUST NOT be merged into the public branch.

#### Scenario: A user obtains the public source

- **WHEN** the user checks out the public maintenance branch
- **THEN** complete-shutdown, damaged-state restore and final-log-drain implementations are available
- **AND** CLI help works without private runtime configuration
- **AND** machine paths and service identifiers are resolved locally or explicitly configured

#### Scenario: An operator generates local runtime material

- **WHEN** local configuration, certificates, logs or backups are created in the deployment directory
- **THEN** Git ignores those private runtime files
- **AND** tracked examples contain only synthetic values

### Requirement: Portable backups retain legacy ancillary compatibility

The public macOS maintenance tools MUST continue to archive and restore the
whole deployment `bin` directory. Optional admin and client-switching scripts
MUST NOT be required to validate a portable backup. Their presence in an
otherwise valid legacy backup MUST NOT cause its rejection. Existing archive
checksum, path, schema and deployment-location validation MUST remain active.

#### Scenario: Portable and legacy backups are verified

- **WHEN** a valid deployment backup omits optional admin and client-switching scripts
- **THEN** verification succeeds
- **AND** the same backup remains acceptable when those optional scripts are present
