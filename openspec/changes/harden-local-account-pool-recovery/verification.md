# Publication validation — 2026-09-21

Base: public 1.24.0 maintenance commit
`9e932343a003d8caf229ef8e4b0d5e045705d0ea`. The maintenance branch preserves that
baseline's application, pricing and timing contracts. Package/application,
frontend, Helm and lockfile versions were checked together at `1.24.0`.

Environment: Python 3.13.15, AnyIO 4.14.0. Validation imports the application from
the publication checkout. All synthetic account/transport tests use isolated
state; no production credential database is opened by these test commands.

## Checks

- `pytest tests/unit tests/test_request_logs_options_api.py -q --timeout=90`:
  6,858 passed, 3 failed, 71 skipped on the initial full run. All three failed
  cases passed in the targeted follow-ups below; the validated unit selection
  therefore covers 6,861 passing cases, not a claim of one all-green full run.
- The existing unpriced Model Source cost test still expected zero, contrary to
  the base's unknown-cost contract. It now verifies `None`. The soft-affinity
  test now requires a retained TTL mapping while keeping a reauthentication
  owner unselectable. Both complete affected test files: **67 passed**.
- The remaining failure was a loopback HTTP-proxy/WebSocket smoke test blocked
  by the filesystem/network sandbox. The identical case passed with local
  socket permission: **1 passed**. It does not call a real model service.
- Skips: 68 Helm-rendering cases require Helm, unavailable in this environment;
  three existing tests were superseded by per-account locking. No new skip was
  introduced by this maintenance change.
- Integration selection: HTTP bridge, direct WebSocket, usage-refresh scope,
  load-balancer behavior, output-timing migration, generation speed, pricing
  migration and request usage capture: **370 passed**, no skipped cases.
- `ruff check .`, `ruff format --check .`, `ty check`, proxy architecture checks,
  release-version consistency, `uv lock --check --offline`, `git diff --check`
  and strict OpenSpec validation passed.

Public baseline timing tests were retained during the three-way test merge.
The renamed unsent-operation rollback test is parameterized to cover both newly
created and rebound operations rather than dropping the old case.

The complete GitHub CI matrix, Docker/Helm smoke, PostgreSQL service jobs,
production rollout and real two-account load acceptance are not claimed by this
record. This is source-branch publication; a future merge/release must meet the
repository's current-head CI and review gates.
