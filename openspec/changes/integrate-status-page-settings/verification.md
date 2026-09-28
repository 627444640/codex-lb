# v1.24.3 integration verification — 2026-09-29

## Git scope and provenance

The user authorized combining the independent HTTP/SSE optimization and the
status-page Settings integration into the local `v1.24.3` branch.

- Base: `v1.24.2` at `79ae33af840526e833fbc797eb19e08edbca0b63`.
- Status-page source: `codex/status-page-settings` at `d9973baf`; retained as a
  separate feature commit and merged by `0ef7908a`.
- Stream optimization: `feat` at `f353140e`; merged by `49290327`.
- Both normal merges completed without conflicts. Their histories remain intact.

This integration does not publish a GitHub release/tag or install/restart the
running service. The independent public monitor remains a separate service;
this repository adds its administrator controls and private connector in Settings.
Package metadata stays at the existing internal `1.24.0` value; `v1.24.3` names
the Git integration branch, not an already deployed package.

## Combined validation

- Complete Python unit selection: **6,932 passed, 71 skipped**. Of the skips,
  68 require Helm and three are existing superseded locking scenarios.
- Combined status/auth/proxy/bridge/WebSocket/timing/request-log selection:
  **2,294 passed**. This selection overlaps the full unit selection.
- Deployment-management unit tests: **42 passed** using isolated data/mocks.
- Complete frontend suite: **1,141 passed across 147 files**.
- Frontend ESLint, TypeScript and production build passed.
- Full Python Ruff lint, formatting and typing passed; proxy architecture passed.
- Strict OpenSpec 1.11.0 validation: **59 main specifications passed**.
- Migration graph still has one head:
  `20260921_000000_merge_local_timing_and_stale_recovery`. Neither feature adds
  or edits a database migration.

The inherited three formatting files, eight nullable-row typing diagnostics,
and 22 placeholder Purpose sections have been reconciled without changing
application requirements. Three additional stale unit-test issues are fixed:
request-count ties no longer assert the obsolete monetary ordering, and the
Prometheus-absence fixture intercepts the production import loader and restores
both module-registry entries and parent-package attributes.

## Browser evidence

All **3 Playwright checks passed** against a freshly built dashboard and an
isolated backend/database on a random loopback port:

1. Existing dashboard responses still satisfy frontend contracts.
2. A missing monitor connector returns a real disconnected response and exposes
   no editable status controls.
3. Synthetic connected-monitor responses exercise email saving without replacing
   the existing secret, timezone-aware publication, withdrawal, and horizontal
   layout at 1440-pixel desktop and 390-pixel mobile widths.

The connected case intercepts only the status control API; it does not send an
email or publish a real announcement. Session/Settings routes and built assets
still come from the isolated LB backend. Real SMTP delivery and the independent
monitor's public page are not revalidated by this merge.

The screenshots in `evidence/settings-desktop.png` and `evidence/settings-mobile.png`
contain synthetic values only and were visually inspected. Capture waits for
save notifications to disappear and positions the section below fixed navigation.
No product layout is hidden or changed for the screenshots.

## Deployment handoff

The code merge is complete. Production rollout remains explicitly deferred and
unchecked in tasks.md. A later rollout must use the existing controlled deployment
procedure, preserve private monitor connector/SMTP credentials and production
history, and verify the real monitor connection after installation. The present
results are local integration evidence, not cloud-CI or production acceptance.
