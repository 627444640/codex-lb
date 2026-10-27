## 1. Reproduction and ownership

- [x] 1.1 Run the known single-write lifecycle canary without xfail and confirm redundant writes.
- [x] 1.2 Serialize request-state release and terminal finalization without changing failure recovery.
- [x] 1.3 Add explicit concurrency, cancellation and retry regressions; make the seeded single-write canary pass.

## 2. Verification

- [x] 2.1 Run the proxy lifecycle and affected reservation/HTTP bridge/websocket test slices.
- [x] 2.2 Run lint, typing, architecture and strict OpenSpec checks.
- [ ] 2.3 Verify current-head CI and review state before integration.
