## 1. Public request diagnostics

- [x] Add typed internal aggregation helpers for a bounded 24-hour request-quality window.
- [x] Map known error codes to public-safe categories and guidance, excluding raw messages and private identifiers.
- [x] Extend the public response with request-quality and incident-summary fields without changing the existing live request contract.

## 2. Status-page presentation

- [x] Separate infrastructure readiness wording from model-request quality wording.
- [x] Render the recent request-quality panel and a compact incident summary for idle and active windows.
- [x] Add DOM regression coverage for current-window idle with recent error categories and for public-safe rendering.

## 3. Validation and controlled rollout

- [x] Run monitor Python tests, status/FAQ/report UI tests, JavaScript syntax checks and formatting/lint checks available in this checkout.
- [x] Run strict OpenSpec validation with the cached CLI.
- [ ] Back up the monitor runtime, install the validated source/runtime files, restart only the independent monitor, and read back API/page/listener/gateway checks.
- [ ] Record deployment evidence and keep the branch commit separate from the installed runtime until parity is verified.
