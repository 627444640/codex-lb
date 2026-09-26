## Why

This deployment is an internal service. The operator requires no anonymous usage reporting, no monetary billing, and request-level source-IP visibility while preserving existing service operation and historical data.

## What Changes

- **BREAKING** Remove anonymous telemetry scheduling, transmission, identity-generation paths, API routes, settings, and dashboard UI. Old environment variables cannot reactivate it.
- Stop monetary estimation and monetary/price-weighted credit admission or settlement; keep input, output, cached-input, cache-write, and total token accounting and token limits.
- Remove money and price configuration from dashboard, reports, API-key usage, and model-source forms. Preserve historical stored prices, costs, limits, and telemetry columns as inert compatibility data.
- Show the existing nullable client IP on request-log rows, and complete trusted source-IP propagation for client-originated proxy operations that currently omit it.
- Validate in isolated development environments and synthetic databases. No production configuration, installed package, database, or process changes are part of implementation.

## Capabilities

### New Capabilities

- `internal-token-usage`: token-only accounting and data-preserving retirement of monetary controls for this internal distribution.

### Modified Capabilities

- `telemetry`: retire anonymous collector traffic and its user-facing controls while retaining schema history.
- `api-keys`: preserve token controls, reject new monetary controls, and ignore retained historical money limits in traffic admission.
- `proxy-runtime-observability`: expose existing trusted client IP on log rows and preserve token evidence without new cost estimation.
- `frontend-architecture`: replace monetary displays with token and request metrics.
- `responses-api-compat`: retain token settlement without duration-based or model-source monetary billing.
- `images-api-compat`: record actual image token evidence without price calculation.
- `quota-phase-planner`: retire monetary budgets and use token/request demand while preserving non-monetary scheduling guards.

## Impact

Backend lifecycle/configuration, request accounting, API-key limits, model-source editing, proxy log metadata, dashboard/report components, and associated tests/docs. Existing Alembic history and database schema remain unchanged. Shared encryption, local usage logs, Prometheus, and optional OpenTelemetry tracing remain independent.
