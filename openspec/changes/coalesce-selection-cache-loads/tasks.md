## 1. Coalesced loading

- [x] 1.1 Reproduce duplicate same-scope loads at the public selection boundary.
- [x] 1.2 Add per-scope load coordination with cleanup and preserve the cache-hit path.
- [x] 1.3 Verify same-scope coalescing, distinct-scope independence, cancellation and invalidation behavior.

## 2. Acceptance

- [x] 2.1 Run cache/selection/invalidation regression tests, typing, lint and architecture checks.
- [ ] 2.2 Publish the bounded-cache and coalesced-load refinements together as one focused cache PR on current main; verify current-head CI before merge.
