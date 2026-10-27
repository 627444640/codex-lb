## 1. Reproduction and implementation

- [x] 1.1 Reproduce excessive, disabled and expired snapshot retention in deterministic regression cases.
- [x] 1.2 Bound resident scopes and reclaim expired snapshots while preserving generation fencing.
- [x] 1.3 Verify public selection reloads evicted scopes without crossing account boundaries or leaking leases.

## 2. Verification

- [x] 2.1 Run related cache, selection, invalidation and lifecycle tests; record the existing skip and xfail.
- [x] 2.2 Run lint, formatting, changed-file typing and architecture checks.
- [ ] 2.3 Verify current-head CI and review state before integrating into main.

## Workflow follow-up

- Synchronize the delta and archive only after verification and review requirements are satisfied.
