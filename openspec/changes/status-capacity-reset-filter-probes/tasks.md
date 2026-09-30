## 1. Capacity reset display

- [x] Add a public weekly reset timestamp without changing the existing
  `weekly_capacity` scalar helper contract.
- [x] Render the reset timestamp in the seven-day card with Asia/Taipei
  formatting and unknown handling.
- [x] Add regression coverage for known and unknown reset values.

## 2. Probe filtering and incidents

- [x] Exclude case-insensitive Luna model rows before request aggregation and
  timing metrics.
- [x] Verify Luna-only errors do not create request incidents while non-Luna
  errors retain current behavior.
- [x] Preserve existing historical monitor events and email records.

## 3. Validation and rollout

- [x] Run monitor tests, lint/format checks and inspect the final diff. The
  repository OpenSpec CLI is unavailable in this environment, so strict CLI
  validation remains an explicit limitation.
- [x] Install the matching monitor source/runtime, restart the monitor, and
  read back the public capacity reset field and incident behavior.
