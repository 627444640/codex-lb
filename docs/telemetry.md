# Anonymous telemetry retired

Anonymous collector reporting has been removed from this internal distribution. This page remains available so earlier documentation links still resolve.

The build contains no anonymous registration or activation flow, signing-identity generation, periodic snapshot sender, opt-out sender, consent/preview API, or dashboard telemetry controls. Old `CODEX_LB_TELEMETRY_ENABLED` and `CODEX_LB_TELEMETRY_ENDPOINT` values cannot restore the removed feature. Removal does not send a final opt-out request.

## Preserved data and observability

Existing telemetry consent and encrypted identity columns remain inert for database compatibility. Historical migrations remain intact; no cleanup of those columns or other service data is required. Shared account-encryption keys, credentials, request logs and token history are preserved.

Local request logging, token accounting, health checks, routing diagnostics, explicitly configured metrics/tracing, and upstream rate-limit protocol events continue independently. They do not feed the retired anonymous collector.

## Deployment and older builds

The behavior described here applies to this internal build. Editing the development checkout does not change a separately installed running service. Deployment and runtime verification remain separate operations.

If an older executable is retained for rollback, retain its operational `CODEX_LB_TELEMETRY_ENABLED=false` override. An old executable may still implement its original telemetry behavior. This page makes no claim to delete data previously received by an external collector.

See [Internal Usage](internal-token-usage.md) for the related token-only policy and data-preservation boundary.

---

*Source of truth: [telemetry](https://github.com/627444640/codex-lb/tree/v1.24.1/openspec/specs/telemetry) · [internal-token-usage](https://github.com/627444640/codex-lb/tree/v1.24.1/openspec/specs/internal-token-usage)*
