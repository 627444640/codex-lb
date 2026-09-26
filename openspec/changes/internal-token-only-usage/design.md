## Context and decisions

The fixed source baseline is `a5836f109dac20efed9231653ab72fc5ce1abff6` on `v1.24.1`. Production runs a separate uv tool installation and is already configured to disable anonymous telemetry. Development occurs only in the canonical source checkout.

Remove the anonymous collector implementation entirely. Preserve its three unused ORM columns and historical Alembic revisions; dropping them would change data and schema unnecessarily. There is no opt-out send during removal. Unregistered old API paths follow normal framework 404/405 behavior, without a tombstone handler.

For monetary accounting, stop price lookup and new cost generation at production paths. Keep stored historical amounts and compatible response shapes where necessary, without recomputing historical records. Existing cost/price-weighted credit limit records remain inert and must survive unrelated token-limit edits; token reservation and settlement remain authoritative. Price forms omit obsolete fields, and updates preserve old model prices when fields are absent. This is fixed internal behavior, with no new feature flag that can turn billing back on.

`request_logs.client_ip`, its index, API mapping, trusted-proxy resolver and bridge forwarding already exist. Reuse them; do not add a migration or trust raw forwarded headers unconditionally. Complete client-originated transcription, file operations, thread goals, control operations, and explicit warmup propagation. Background warmup/automation work retains null when no client exists. Preserve guest redaction.

## Validation and operational boundary

Tests use fresh temporary directories, explicit temporary encryption-key paths and synthetic SQLite databases. Legacy monetary and telemetry values are seeded synthetically and checked for preservation. No test may target production listeners, data, or keys. Frontend build generates a fresh static bundle; package inspection must find no anonymous-telemetry implementation or collector endpoint.

Verify telemetry absence even with old enable variables, ordinary settings/health and token accounting, monetary-limit inertness, edit preservation, trusted-IP handling and guest privacy. UI tests retain meaningful token assertions and assert that monetary controls and telemetry requests are absent.

Deployment is separate from source validation. Do not restart or migrate the running service while implementing this change. Preserve a reviewable artifact and state the installed-versus-source boundary explicitly.
