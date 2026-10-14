## ADDED Requirements

### Requirement: Official provider status is optional and server-side

When `official_status.enabled` is true, the monitor SHALL periodically fetch
the configured fixed HTTPS OpenAI Statuspage summary endpoint without
credentials, validate a bounded JSON response, and normalize the provider
state. When the setting is absent or false, the monitor SHALL make no provider
request.

#### Scenario: Official status is disabled by default

- **WHEN** a monitor configuration has no enabled official-status setting
- **THEN** the monitor does not make an outbound provider-status request
- **AND** the public response omits or marks `official_status` unavailable

#### Scenario: Provider response is valid

- **WHEN** the provider returns a valid summary response
- **THEN** the monitor exposes a normalized provider state, provider page
  update time and local fetch time
- **AND** the bounded component and active-incident summaries are available to
  the public page

### Requirement: Official state remains separate from local health

The public status response SHALL expose provider state under a separate
`official_status` object. Provider state SHALL NOT change local aggregate
status, local components, readiness history, local incidents or email alerts.

#### Scenario: Provider reports degradation while the gateway is healthy

- **WHEN** the provider indicator is `minor` and all local components are
  operational
- **THEN** the provider card shows degraded
- **AND** the local status banner and local readiness history remain based on
  local observations

### Requirement: Failed or stale provider data is unknown

Timeouts, non-success responses, malformed or oversized JSON, unknown status
enums and expired provider samples SHALL produce an unknown/stale provider
state. The monitor MUST NOT present old provider data as current green data and
MUST NOT expose raw upstream errors, headers, credentials or unbounded payloads.

#### Scenario: Provider fetch fails

- **WHEN** the provider request times out or returns an invalid response
- **THEN** the public card states that the official status is unavailable or
  waiting for confirmation
- **AND** local status, incidents and request quality are unchanged

### Requirement: Public UI identifies the official source

The status page SHALL render a separate “OpenAI 官方状态” section with the
source link, provider description, provider update time, local fetch time and
bounded active incident summaries. The page SHALL state that provider status
is an aggregate signal and does not prove a local authenticated model request.
The browser SHALL fetch only the same-origin public status API.

#### Scenario: Visitor reads official status

- **WHEN** a fresh official provider sample is available
- **THEN** the visitor sees the normalized state and source metadata
- **AND** the source link opens the official status page in a separate tab
