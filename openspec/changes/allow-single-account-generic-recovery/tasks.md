## 1. Selection change

- [x] 1.1 Extend the generic-backoff fallback condition so exactly one hard-eligible account in backoff is selectable even when `allow_backoff_fallback=False`; verify with a focused selector test.
- [x] 1.2 Preserve hard-state filtering, request exclusions, quota/rate-limit/cap checks and existing multi-account fallback; verify positive and negative selector tests.

## 2. Verification and publication

- [x] 2.1 Run the focused selector tests and the existing transient-retry suite; record exact outcomes.
- [x] 2.2 Run Ruff/format, ty and strict OpenSpec validation; record results.
- [x] 2.3 Audit the publication diff for privacy and publish a focused PR linked to #18/#15; do not merge or deploy without separate gates.
