## 1. Energy meter UI

- [x] Replace the native progress bar with a 40-block accessible energy meter
  and green/yellow/red capacity thresholds.
- [x] Preserve percentage, reset-time and unknown-capacity behavior.
- [x] Add the DOM-level energy meter regression test and Makefile target.

## 2. Validation and rollout

- [x] Run monitor, UI, lint/format and JavaScript syntax checks, deploy the
  matching static assets, and restart the monitor.
- [x] Read back the LAN page/API and verify the energy meter after deployment.
