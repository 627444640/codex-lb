# Measurement scope and evidence

## Synthetic reproductions

A synthetic ten-token response delivered in one chunk with a 5 ms interval before completion yields 2,000 TPS under the old formula without evidence of sustained output speed. Separately, a virtual-clock test can hold upstream completion at 1,000 ms and TTFT at 500 ms, then vary only settlement delay from 0 to 2,000 ms: the old recorded total latency changes from 1,000 to 3,000 ms. These reproduce different problems: under-sampled output delivery and a completion timestamp polluted by bookkeeping.

Public problem report: [Soju06/codex-lb#2443](https://github.com/Soju06/codex-lb/issues/2443). All examples in this document are synthetic; operational records are outside the source change.

Source-routed parsing also lost usage/metrics in legal multi-line SSE and accepted optional timing values whose sum could overflow. These are included because they affect the same measured fields and may interrupt otherwise valid responses.

## Design limits

- Non-reasoning TPS needs a non-reasoning start. An earlier reasoning summary remains useful TTFT evidence but must not be the denominator anchor for visible-output speed.
- Two output chunks and a 100 ms observation window are minimum evidence for a useful estimate, not proof of internal model decode speed. The first chunk may contain multiple tokens, and network framing remains observable. No tokenizer guess or artificial denominator is introduced.
- A qualified long-window response may legitimately show a high observed rate; there is no speed cap.
- Old logs lack output sampling metadata. They retain clearly labeled legacy estimates where possible; their original timestamps are never backfilled. Daily qualified TPS is null without eligible samples and reports its sample count.
- The report's existing inclusion of soft-deleted historical usage is intentional and remains unchanged.
- The scenario title "Missing daily speed data is zero-filled" is retained for OpenSpec scenario continuity; zero-filling now applies to the sample count, while missing latency/speed medians are null.
- Existing HTTP attempt versus WebSocket request-state anchors remain intact and are explained in the UI. Client end-to-end network/rendering latency and hidden reasoning start time cannot be reconstructed by the gateway.
- Sources that report their own metrics keep those timing values; they do not acquire invented local output chunk metadata.

## Validation boundary

Use deterministic virtual-clock tests and real proxy/API paths with local stubs. Validate the release artifact and migration upgrade/downgrade against isolated database fixtures, preserving original fields and unknown historical timing metadata. Operational validation records are outside this source change.

## Completed validation (2026-09-15)

- Backend: 8,887 passed, 106 skipped; frontend: 1,165 passed. Real-backend browser smoke, Python/frontend static checks and proxy architecture checks passed. Before publication, fixture-only privacy cleanup was rechecked with 44 backend and 40 UI tests; runtime implementation was unchanged.
- Strict change validation passed; all 57 main specs passed standard validation. Global strict validation still reports 22 pre-existing Purpose placeholder warnings in unrelated specs.
- Migration upgrade/downgrade checks passed, including preservation of original request fields and unknown historical timing metadata. A rollback rehearsal verified that an inserted synthetic request survives downgrade and the previous package accepts the resulting schema.
- Two accounting assertion mismatches were reproduced on the untouched base commit and synchronized with its existing unrounded cost/cache-write response fields; production pricing logic was unchanged.
