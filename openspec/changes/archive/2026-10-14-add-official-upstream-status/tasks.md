## 1. OpenSpec and configuration

- [x] Add the proposal, design and delta requirements for the optional official
  provider status source.
- [x] Add validated default-off configuration fields and document the operator
  contract.

## 2. Backend collection and public contract

- [x] Implement bounded server-side OpenAI Statuspage summary fetching and
  normalization.
- [x] Add `official_status` to snapshots and public output with stale/unknown
  semantics while preserving local status, history and alert boundaries.
- [x] Add Python regression tests for success, failures, schema drift, stale
  data, privacy filtering and default-off behavior.

## 3. Public status UI

- [x] Add the separate official-status card, source link, timestamps, bounded
  incidents and component display.
- [x] Add DOM regression coverage for fresh, degraded and unknown states.

## 4. Documentation and validation

- [x] Update monitor and status-page operator documentation.
- [x] Run the status monitor tests and strict OpenSpec validation when the
  `openspec` CLI is available; record unavailable validation explicitly.
