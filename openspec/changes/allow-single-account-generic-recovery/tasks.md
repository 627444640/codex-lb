## 1. Selection change

- [x] 1.1 Extend the generic-backoff fallback condition so exactly one hard-eligible account in backoff is selectable even when `allow_backoff_fallback=False`; verify with a focused selector test.
- [x] 1.2 Preserve hard-state filtering, request exclusions, quota/rate-limit/cap checks and existing multi-account fallback; verify positive and negative selector tests.

## 2. Observation

- [x] 2.1 Emit the structured single-account recovery event with bounded fields; verify the log-capture test.
- [x] 2.2 Verify normal selection does not emit the recovery event and fallback leaves backoff timestamps unchanged.

## 3. Verification and publication

- [x] 3.1 Run the focused selector tests and the existing transient-retry suite; record exact outcomes.
- [x] 3.2 Run Ruff/format, ty and strict OpenSpec validation; record results.
- [x] 3.3 Audit the publication diff for privacy and publish a focused PR linked to #18/#15; do not merge or deploy without separate gates.
