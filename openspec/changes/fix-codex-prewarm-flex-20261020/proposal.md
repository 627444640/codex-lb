## Why

Live Codex WebSocket prewarms for gpt-5.6-luna and gpt-6-astra explicitly
send service_tier=flex with generate=false. The authoritative subscription
catalog advertises the models but not Flex, so account selection rejects the
no-generation prewarm with no_plan_support_for_model before reaching upstream.

## What Changes

- For verified Codex no-generation prewarms only, omit an unadvertised Flex
  tier before quota reservation, account selection and upstream serialization.
- Derive compatibility from the existing authoritative model registry for any
  model; keep advertised Flex, other tiers, unknown catalog state and normal
  generation requests unchanged.
- Record a structured normalization event and verify the actual WebSocket
  endpoint, including the subsequent normal turn on a prewarm connection.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- responses-api-compat: Normalize unsupported Flex for verified no-generation prewarms.
- model-catalog-compat: Document the narrow prewarm exception to explicit-tier filtering.

## Impact

Two backend files; no schema, account-state, credential, model entitlement or
frontend change. Production deployment must preserve unrelated local work and
the installed release, with backups, a drained backend restart and readback.
