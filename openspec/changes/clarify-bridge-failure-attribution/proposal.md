## Why

HTTP Responses bridge admission can report a local recovery gate as an upstream timeout. Operators and retry consumers must distinguish a future circuit cooldown, a busy half-open probe, a generation conflict, and unavailable persistence without granting new replay rights. This change establishes synthetic regression evidence before making narrowly scoped error-contract changes.

## What Changes

- Characterize the existing pre-response circuit, durable generation claims, operation identity, same-attempt deduplication, and sibling UNKNOWN/ACKNOWLEDGED behavior.
- Represent bridge admission decisions with typed reasons and an optional genuine retry deadline while preserving existing admission and replay guards.
- Report `bridge_session_cooldown` only for a proxy-owned gate with a future local or durable cooldown; preserve the streaming/non-streaming error contracts and avoid treating the new code as ambiguous upstream execution.
- Distinguish half-open occupancy, generation conflicts, and persistence failures without inventing retry deadlines.
- Preserve all current breaker defaults, the three circuit failure classes, dead-anchor cleanup, request budgets, owner fences, and account/API-key settlement order.
- Publish only source, synthetic tests, and sanitized design/verification summaries. Keep production data and raw verification logs local.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: explicit bridge admission outcomes and truthful cooldown error envelopes, including already-started SSE and owner-forwarded requests.
- `proxy-runtime-observability`: bounded gate-reason diagnostics that separate local rejection from an upstream attempt and preserve physical-attempt attribution.

## Impact

- Proxy bridge retry-circuit/admission helpers, existing API error consumers and targeted unit/integration tests.
- No database migration, new setting, endpoint quarantine, TTFT routing, blanket continuity exemption, or change to the one-shot verified recovery authorization chain.
- Existing `/api/accounts/admission-breakers` and history-cache dashboard contracts remain unchanged.
- GitHub tracking: [recovery-reliability plan #15](https://github.com/627444640/codex-lb/issues/15). This is the first independently reviewable stage, not completion of the whole plan.
