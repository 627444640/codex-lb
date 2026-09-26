# telemetry Specification

## Purpose

Define the retirement of anonymous collector functionality in the internal distribution while preserving historical database compatibility. See [context.md](context.md) for the scope and rollback boundary.

## Requirements

### Requirement: Anonymous collector functionality is retired in the internal distribution

The internal distribution MUST NOT register an anonymous instance, generate or use a telemetry signing identity, activate a collector session, transmit usage snapshots or opt-out events, or start anonymous-telemetry scheduling tasks. It MUST NOT expose telemetry consent or preview APIs, dashboard controls, consent dialogs, or data-preview UI. Legacy enable and endpoint environment variables MUST NOT restore this functionality.

#### Scenario: Legacy enabled configuration cannot reactivate telemetry

- **GIVEN** stored consent is enabled and `CODEX_LB_TELEMETRY_ENABLED=true` remains in the environment
- **WHEN** the internal application starts and the dashboard opens
- **THEN** no anonymous-telemetry task, browser API request, or collector connection is created
- **AND** no signing identity is generated or decrypted

#### Scenario: Old telemetry API is unavailable

- **WHEN** a client requests the former telemetry settings or preview route
- **THEN** no telemetry handler processes the request
- **AND** ordinary unregistered-route behavior applies without an opt-out transmission

### Requirement: Historical telemetry storage remains inert

The three historical `dashboard_settings` telemetry columns and their ORM mappings MUST remain compatible with existing databases. Existing consent, instance identifiers, encrypted signing material, and unrelated settings MUST NOT be changed by this retirement. The historical Alembic revision and its descendants MUST remain intact. Retirement MUST NOT perform data cleanup, introduce a new migration, or replace the shared encryption key.

#### Scenario: Existing database starts without a telemetry migration

- **GIVEN** the database is at the existing current migration head
- **WHEN** the internal distribution starts or an unrelated dashboard setting changes
- **THEN** historical telemetry values remain unchanged
- **AND** account credentials, authentication material, logs, and usage history remain intact

### Requirement: Anonymous retirement preserves local operational observability

Request logging, token usage, health checks, routing diagnostics, operator-configured metrics and tracing, and upstream protocol events MUST retain their independent behavior. These features MUST NOT be connected to the retired anonymous collector.

#### Scenario: Requests retain local evidence

- **WHEN** the proxy handles a request after anonymous telemetry removal
- **THEN** normal local request logs and token usage remain available
- **AND** their creation does not schedule anonymous reporting
