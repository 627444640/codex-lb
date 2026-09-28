## ADDED Requirements

### Requirement: Managed deployment authentication policy
The system SHALL support `CODEX_LB_DEPLOYMENT_AUTH_POLICY=standard|managed`, defaulting to `standard`. Managed mode SHALL require an administrator password and proxy API-key authentication for HTTPS exposure while permitting read-only guests with an optional password. It SHALL expose read-only policy capabilities as `deploymentAuthPolicy` in settings responses.

#### Scenario: Managed guest access preserves serving
- **WHEN** an administrator enables guests or sets, changes or removes the guest password
- **THEN** existing guest read/write boundaries remain in effect
- **AND** HTTPS remains running without restarting its proxy

#### Scenario: Required authentication cannot be disabled
- **WHEN** a managed deployment receives a settings update disabling API-key authentication or an administrator-password removal request
- **THEN** it returns HTTP 409 with code `deployment_policy_violation` and the affected field
- **AND** no settings, credentials, TOTP or sessions are changed, including other fields in the same request

#### Scenario: Initialization and standard compatibility
- **WHEN** an installation uses standard mode or a managed installation initializes missing credentials
- **THEN** standard behavior and incremental managed initialization remain available
- **AND** repeating managed initialization preserves guest configuration

### Requirement: Installed read-only policy check
The system SHALL provide `codex-lb auth-policy check --json` using the same policy definition as application mutation validation. Schema version 1 SHALL report mode, requirements, boolean state, allowed and violation codes, with exit codes 0, 1 and 2 for allowed, denied and unknown. The SQLite check SHALL use read-only query-only access and SHALL NOT create missing databases, run migrations, read credential values, or initiate network calls.

#### Scenario: Deployment consumes installed policy
- **WHEN** the macOS supervisor or status command evaluates HTTPS exposure
- **THEN** it invokes the configured installed executable with the backend environment and a bounded timeout
- **AND** it requires a valid managed policy result and the initialization marker

#### Scenario: Out-of-band authentication failure
- **WHEN** required authentication is removed outside the application or the installed policy cannot be determined
- **THEN** the HTTPS supervisor retains its bounded emergency shutdown protection
- **AND** status distinguishes unknown policy state from a known policy violation
