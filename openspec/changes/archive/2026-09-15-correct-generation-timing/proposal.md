# Correct generation timing and sample quality

## Why

WebSocket/bridge total latency currently includes post-response API-key settlement; SSE and abort paths can include cleanup waits. Bridge TTFT is observed at downstream queue consumption. A synthetic ten-token response delivered in a five-millisecond tail window is displayed as 2,000 TPS without a quality qualification. Reasoning-summary TTFT is also used as the start of non-reasoning TPS, and empty report samples are rendered as measured zero.

## What Changes

- Capture event receipt and terminal/abort timestamps before asynchronous bookkeeping on SSE, WebSocket and HTTP bridge; keep routing and settlement ordering unchanged.
- Persist nullable first non-reasoning output latency and output chunk count; preserve historical unknowns and recognize full terminal-only output without inventing timings from usage.
- Calculate request TPS once on the backend, expose sample status, distinguish legacy estimates, and exclude insufficient or incomplete samples from daily speed statistics.
- Treat report latency/speed with no eligible samples as null, expose eligible TPS sample counts, and explain gateway TTFT and estimated output TPS in the UI.
- Synchronize the existing non-reasoning TPS definition with the main specification.

## Impact

Two nullable request-log columns and an additive request-log API contract; daily median fields become nullable. Existing history is not rewritten. Tests cover receive/settlement/queue timing, sample qualification, API/report consistency, migration and UI behavior. Migration validation includes downgrade/re-upgrade and original-field preservation.
