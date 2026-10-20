# Verification

Validation completed on 2026-10-19 (Asia/Taipei) on
`fix/status-quota-semantics-20261019`.

- `make test-status-monitor` passed: 49 Python tests, 2 FAQ DOM tests and 1
  status-page DOM test.
- `PYTHONPATH=deploy/status-monitor .venv/bin/pytest -q deploy/status-monitor/tests`
  passed: 49 tests, 16 subtests.
- `.venv/bin/pytest -q tests/unit/test_status_page_service.py
  tests/integration/test_status_page_settings.py` passed: 12 tests.
- `frontend/node_modules/.bin/vitest run` for the status-page Settings and
  Settings page suites passed: 11 tests.
- `frontend/node_modules/.bin/tsc -b` and the targeted ESLint invocation
  passed. Ruff check and format checks passed for the changed monitor files.
- `node --check deploy/status-monitor/monitor/static/status.js` passed.
- Manual contract review confirmed the public response still omits `pool`,
  account identifiers and account counters, while authenticated Settings
  receives only the sanitized aggregate quota object.
- `openspec validate --specs` could not run because the `openspec` executable is
  not installed in this environment (exit 127). The change artifacts, main
  spec/context sync, requirement headings, task checkboxes and source/spec
  paths were checked manually; strict CLI validation remains unverified.

## Deployment and live readback

Deployment completed on 2026-10-19 (Asia/Taipei) from source merge commit
`b84dea8c` into the independent runtime `/Users/a123/codex-lb-monitor`.

- The five changed monitor files were backed up under the private rollout
  snapshot `runtime/rollouts/status-quota-semantics-20261019T123112+0800/before`
  before replacement. Runtime/source SHA-1 hashes matched for collector,
  store, control, overview HTML and status JavaScript.
- Only `com.local.codex-lb-monitor` was restarted. LaunchAgent state returned
  `running` with a new process; the core LB and existing Caddy service were not
  restarted.
- Loopback `/health`, loopback `/api/status`, LAN HTTPS `/`, and LAN HTTPS
  `/api/status` all returned HTTP 200. Loopback and LAN selected API fields
  matched, and the LAN-served `static/status.js` hash matched source.
- The live public API returned `status=operational`, `stale=false`, weighted
  capacity `32.0%`, quota `operational` with detail `仍有可路由额度`, and a
  separate `quota_warning=degraded` with detail `部分账号余量低于安全线` and
  `advisory=true`. The quota component did not return `额度不足`.
- The authenticated loopback Settings response returned HTTP 200 with a
  sanitized summary: current capacity about `31.5%`, lowest remaining `0.0%`,
  `active_accounts=2`, `quota_ready=1`, `quota_exhausted=1`, routability
  `operational`, and low-quota status `degraded`. The public response still
  omitted `pool`, account counts and account identifiers.

The live account pool was at 32% during this readback rather than the earlier
41% snapshot; the deployment verified the same semantic path without changing
or fabricating quota data. Authenticated real-model generation remains outside
this deployment check.
