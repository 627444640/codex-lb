# Verification: official pricing and unknown-cost limits

Verified 2026-09-17 against public baseline 53674699, retaining the existing accounting and TTFT/TPS implementation. Runtime changes are limited to six backend files; there is no new database migration.

## Evidence

- Compared 201 supported Standard/Flex/Fast short/long-context rate values with the official pricing snapshot: no mismatches. GPT-5.4 Flex cached input uses the exact documented 50% discount (0.125) rather than the rounded display value (0.13).
- Final candidate backend regression: **706 passed** across 16 targeted pricing, quota, source, request-log, HTTP/WebSocket and timing suites.
- Final candidate frontend regression: **177 passed** across seven dashboard/schema/formatter and TPS/queue chart suites.
- Frontend TypeScript build, production bundle and wheel build passed.
- `ruff check app tests`, `ty check app` and `git diff --check` passed.
- Full `ty check` has three pre-existing test-only diagnostics, independently reproduced on the unchanged baseline: an object/integer comparison in the WebSocket suite and two nullable mock await_args accesses in the HTTP bridge suite. No new diagnostic was introduced.
- `make ci` was attempted before publication but stops because Bun is unavailable in the local environment. The full Docker, Helm and PostgreSQL CI matrix is not claimed as passing.
- Alembic retains the single output-timing head. Offline installation, exact-code rollback and existing-row preservation checks passed on isolated copies.
- Independent review verified 1,000 valid image modality partitions against a separate formula. Unknown actual-model/tier settlement preserves cost allowance, settles actual token counters, remains idempotent and distinguishes explicit zero.
- Synthetic browser checks verified the precise-cost, history and unknown-pricing UI. The three images in evidence/ use tracked synthetic fixtures, not production accounts.

## Specification checks

The changed capabilities pass strict OpenSpec validation; all 57 main capabilities pass standard validation. Full-repository strict validation retains 22 unrelated Purpose-placeholder warnings from the baseline.

## Publication boundary

Application Python files were compared with the validated deployment wheel and found identical. Publication includes source, tests, normative specs and synthetic UI evidence. Machine-specific configuration, credentials, databases, deployment logs and local release intermediates are excluded.
