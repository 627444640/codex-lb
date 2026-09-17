## 1. Published pricing

- [x] 1.1 Add verified variant rates and pricing provenance; check against the official 2026-09-17 snapshot.
- [x] 1.2 Bound model aliases and return unknown for unpublished tiers/context prices; verify pricing and modality regression tests.

## 2. Accounting and presentation

- [x] 2.1 Protect cost-limited admission and preserve unknown final allowances; verify HTTP, WebSocket, explicit-zero and source-pricing paths.
- [x] 2.2 Expose unknown_pricing separately from missing models/usage and preserve historical amounts; verify request-log and dashboard regressions.

## 3. Verification

- [x] 3.1 Run targeted backend/frontend, type, lint, package and schema compatibility checks; document unavailable full-CI checks.
- [x] 3.2 Complete independent review, synchronize specs and archive the verified change.
