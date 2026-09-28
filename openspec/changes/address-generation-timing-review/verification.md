# Verification — 2026-09-28

Mechanical review repairs are implemented; metric-policy and #2112 landing-order
agreement remain outstanding. The change remains active and #2444 remains draft.

- SCIM: all 23 removed keys restored in each of en/ko/zh-CN with upstream values.
- Migration: the new 20260928_000000 revision directly follows the 20260918 merge
  head. Topology against official main is a single head; SQLite round-trip and
  historical-row tests pass. No published migration was modified.
- Fast path: one or 256 canonical post-anchor deltas require exactly three parser
  calls on the stream path. First non-reasoning content after reasoning is inspected
  once without re-encoding the frame. Event counts do not promise nonempty content
  for unparsed canonical deltas; the sample threshold is still a pending decision.
- Routing: delayed finalizer settlement no longer dilutes the existing throughput
  sample. Missing terminal receipt evidence remains null in persisted logs.
- Focused timing/WebSocket recheck: 52 passed. Fast-path regression: 3 passed.
- API/bridge/WebSocket/report/migration integration group: 392 passed.
- Locked frontend (Bun 1.3.14, Vitest 5.0.0): 1,654 passed; lint, typecheck and build passed.
- Complete unit/simulation selection: 10,500 passed, 98 skipped, 1 known xfail.
  Four failures reproduce on unmodified official main f8ffbac2099a113fba54dfd8d77774f5bca80ffa:
  temporary-filesystem refusal, native-egress invalid metadata case events4, and
  two optional-Prometheus import fixtures. Baseline replay: four failed, 14 passed.
  A fifth pre-commit failure compares HEAD's migrations with the edited tree;
  it must be rerun after the repair commit. This is not an all-green unit claim.
- Ruff/format, type checks, proxy architecture, cancellation safety, clock seams,
  settings tiers, migration topology and contributor attribution passed.
- CI-pinned OpenSpec 1.11.0: all 67 main specs and this change passed strict validation.

The source hardening has its own 306 passing tests in #2521. The relocation has
1,434 passing existing streaming tests in #2520. Cloud CI, PostgreSQL-specific
execution and current-head review remain separate gates; no deployment was done.
