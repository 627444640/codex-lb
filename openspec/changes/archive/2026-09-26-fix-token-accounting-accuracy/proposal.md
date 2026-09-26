## Why

The internal build inherits three reproduced accounting defects: negative upstream usage can reduce prior quota, a failed model-source Responses stream can be recorded as successful, and partial usage yields different totals in dashboard and reports. Fix these before merging the internal release while preserving historical data and the running service.

## What Changes

- Validate token usage before quota mutation; malformed or negative counters must not reduce earlier usage, while legitimate reservation refunds remain supported.
- Preserve Responses terminal outcome through model-source forwarding and settlement, record failed/incomplete outcomes accurately, and release unsuccessful reservations consistently with the native path.
- Use the same known-token aggregation in logs, reports, dashboard cards and trends before and after hourly folding. Expose partial usage as partial rather than representing reasoning-only output as complete output.
- Add isolated end-to-end regression coverage for the three audited examples and normal successful requests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `internal-token-usage`: validated usage, terminal outcome preservation, and consistent known-token totals with partial-data semantics.

## Impact

Usage parsing, API-key settlement, model-source Responses forwarding, request-log/dashboard aggregation and display. No database schema change, historical rewrite, new configuration, dependency changes or production rollout. Existing internal changes are checkpointed separately; fixes are implemented on `fix/token-accounting-1.24.1-20260926` and merged locally into `v1.24.1` after verification.
