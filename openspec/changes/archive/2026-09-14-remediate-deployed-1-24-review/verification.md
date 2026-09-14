# 1.24.0 review remediation verification

## Publication scope

This public branch starts at clean upstream v1.24.0 (`84fde5a1`). It contains R01, R04, R05, R06, R07, R08, R09, R11 and the verified admin/guest login error-handling fix. Private macOS deployment changes R02/R03/R10 and their deployment files remain local. No withdrawn deployment history is merged or force-pushed. No production rollout is included.

Before publication, all 1,361 tracked application, frontend and test files were compared byte-for-byte with the fully tested candidate; all matched. Ruff, formatting, type checking, architecture checks and change validation were additionally rerun in this clean public checkout.

## Final validation

| Suite | Result |
|---|---|
| Unit: `pytest tests/unit tests/test_request_logs_options_api.py` | 6,368 passed, 71 skipped |
| Core integration: verified project CI three-shard partition, 100 files | 698 + 675 + 662 = 2,035 passed, 34 PostgreSQL-specific skips |
| Complete HTTP/WebSocket bridge integration | 268 passed |
| E2E | 27 passed, 1 opt-in installed-Codex test skipped |
| Independent PostgreSQL 18.4 | 167 standard-target tests plus 17 auth/quota tests passed; no skips; temporary cluster removed |
| Frontend: `bun run test:coverage` | 146 files / 1,153 tests passed |
| Frontend lint / typecheck / production build | Passed |
| Actual browser against temporary backend | Password setup, invalid-password 401, valid retry, token quota save, credits choice removal/API rejection passed with no global browser errors |
| Python Ruff / format / ty / architecture | Passed |
| OpenSpec | Standard full-spec validation passed; this change and its six changed capabilities passed strict validation |
| Package | Wheel source/assets comparison and independent installation passed; fresh SQLite migration policy OK and no schema drift |

Backend suites used `--timeout=180 --timeout-method=thread`, CPython 3.13.15 and frozen uv.lock. Frontend used Bun 1.3.14 and frozen bun.lock. The final source has no test failures in these executed suites. Initial failures were traced and corrected: old tests expecting distinct tool IDs to collapse, fixtures creating now-unsupported credits, a test bypassing the real file-owner preparation path, and a baseline shared-deadline timer-order assertion. Authentication, file ownership, settlement and quota assertions were preserved or strengthened.

## Verified behavioral boundaries

- **R01:** zstd declared output and native windows are checked before decoding; output is read incrementally. Single-frame and layered-encoding behavior remains. The independent reviewer found a large-valid-budget native-parameter regression; the decoder now uses the validated frame requirement. All 50 ingress tests passed, including 4 GiB and 2^64 configurations, known/unknown-size expansion, invalid input and valid controls.
- **R04:** unsupported credit limits cannot be created or used to admit requests. Administrators can replace legacy rules. Token/cost limits remain visible through `/v1/usage` and are never converted into invented Codex credit units. Upstream account credits remain separate.
- **R05:** every cookie consumer validates the applicable verified credential fingerprint. Password/TOTP rotation, guest independence, ordinary setting changes and issuance races have regression coverage. One fresh read-only candidate reviewer found no concrete remaining authorization bypass.
- **R06:** independent nonblank call IDs and their tool outputs remain distinct; exact historical replays are still suppressed.
- **R07:** event queues retain at most 32 MiB per request and share a 256 MiB process budget. Overflow explicitly fails local delivery while healthy sibling requests, upstream persistence and terminal accounting continue. This is an event-queue budget, not a whole-process memory limit.
- **R08:** password work executes off-loop with two permits. Cancellation retains ownership until native work completes, prevents queued submission and does not commit cancelled credential writes.
- **R09:** cached history advances with the requested cutoff, expires lazily after 30 seconds and is bounded to 32 entries/100,000 rows. SQL/hash work leaves the global lock; snapshot and invalidation-generation tests protect concurrency.
- **R11:** native macOS current RSS permits admission to recover after release. The HTTP test observes 200 → 503 → 200 after a 64 MiB temporary allocation.

A synthetic SQLite benchmark with 100,000 stored rows and a 1,000-row active window reduced retained rows from 100,000 to 1,000 and warm median query time from 183.741 ms to 1.802 ms, with row-by-row parity against a fresh query. This is a local synthetic measurement, not a production throughput claim.

## Limits

The 71 unit skips comprise 68 tests requiring absent Helm tooling and 3 upstream tests marked inapplicable. PostgreSQL-specific SQLite skips were supplemented by an independent PostgreSQL run. Docker/Kubernetes deployment and real-account model traffic were not exercised; those deployment implementations are outside this public change. There was no long-running production load test.

Full-repository OpenSpec strict validation still reports 22 pre-existing Purpose placeholders; normal full-spec and all changed-scope strict validations pass. Cross-replica credential revocation follows existing settings-cache propagation; logout still clears the client cookie without claiming per-cookie server-side revocation. Local tests do not substitute for GitHub merge gates. The package retains the upstream version 1.24.0 and must be identified by this branch and its checksum, not confused with the unmodified official package.

## Public artifact identity

The clean public build produces `codex_lb-1.24.0-py3-none-any.whl` with SHA-256 `b49e9cdd663cc053c35d3009e0df898b2221353da075dbe6c952f50025c23b3f`, identical to the independently installed and tested candidate wheel. Its 587 application source files and 90 frontend assets match exactly. The public source distribution contains no private deployment directory. Implementation commit: `a5ef5458`; subsequent archive records do not modify application code.
