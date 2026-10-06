## 1. Idle status aggregation

- [x] Exclude only the idle request component from page-level severity when its
  fresh request aggregate has zero normal samples.
- [x] Keep request incident debounce behavior unchanged and add regression tests
  for healthy idle and unhealthy infrastructure cases.

## 2. Idle presentation

- [x] Update the status banner and request component copy for the no-sample
  state while preserving stale-data behavior.
- [x] Add UI/static checks for the idle text and no-sample label.

## 3. Validation and rollout

- [x] Run monitor tests, lint/format and JavaScript syntax checks, and inspect
  the diff. The repository OpenSpec CLI is unavailable in this environment, so
  strict CLI validation remains an explicit limitation.
- [ ] Deploy the monitor and restart the service.
- [ ] Read back the LAN status API/page with no normal requests and verify the
  existing gateway/quota failure path still produces a non-operational banner.
