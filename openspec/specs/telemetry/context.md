# Anonymous telemetry retirement

## Decision and scope

The internal `v1.24.1` development line removes the anonymous collector feature rather than relying on a consent setting. The sender, registration/activation flow, signing identity generation and use, snapshot builder, preview/consent API, scheduler and dashboard UI are removed together. Legacy environment variables cannot enable code that is no longer present.

This retirement applies to anonymous usage reporting. It does not remove local request logs, token accounting, upstream rate-limit protocol events, health endpoints, or explicitly configured operational tracing. The word telemetry in those unrelated implementations is not an instruction to delete their functionality.

## Data compatibility

Keep `telemetry_consent`, `telemetry_instance_id`, and `telemetry_private_key_encrypted` as unused ORM/database fields, including their existing defaults and types. Keep the original Alembic revision and every descendant. This avoids database rewrites, schema drift, and a migration-dependent rollback. An unrelated settings edit must not mutate the preserved values.

The encrypted telemetry value is not the shared encryption key. The shared key is still required for account credentials, authentication, OAuth and upstream proxy secrets and must not be deleted or rotated as part of this change.

## Example and rollback boundary

An existing database may contain `telemetry_consent=enabled`, and an old environment may contain `CODEX_LB_TELEMETRY_ENABLED=true`. The internal build still has no telemetry sender, scheduler or preview route and does not generate an identity or issue an opt-out event. No environment flag restores the retired feature.

Deploying an older executable could restore its former behavior. Retain the operational `CODEX_LB_TELEMETRY_ENABLED=false` override while a prior build is kept for rollback. Source changes do not replace the separately installed running service; deployment and authenticated service acceptance are separate operations.

See [the requirements](spec.md), [internal token usage](../internal-token-usage/spec.md), and the [change](../../changes/internal-token-only-usage/proposal.md). The earlier [opt-out signal change](../../changes/add-telemetry-optout-signal/proposal.md) is superseded, not newly verified or archived by this retirement.
