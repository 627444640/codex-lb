## Implementation and source validation
- [x] Preserve the published 1.24.0 accounting and output-timing baseline.
- [x] Implement and test operation-fenced full-context stale-anchor recovery.
- [x] Implement and test bounded lifecycle-only capacity recovery and settlement ordering.
- [x] Test hard ownership, stable temporary soft substitutes and reauthentication boundaries.
- [x] Test sustained overload avoidance and confirmed blocking-window reset recovery.
- [x] Bound detached-session cleanup lock waits and test cancellation/lease cleanup.
- [x] Add tested private SQLite/key restoration and bounded read-only observations.
- [x] Keep all package version fields aligned and pin the tested AnyIO dependency.
- [x] Complete publication-checkout regression and static checks (scope and unavailable jobs in verification.md).

## Separate operational acceptance
- [ ] Publish a release through the repository release process after applicable gates.
- [ ] Deploy with a fresh whole-service backup and independently verify the live service.
- [ ] Validate two real healthy accounts and measure actual workload capacity.

See `docs/operations/sqlite-account-pool-maintenance.md`. Synthetic validation,
offline recovery and private deployment observations do not prove production
capacity. Keep this change active until the relevant acceptance is complete.
