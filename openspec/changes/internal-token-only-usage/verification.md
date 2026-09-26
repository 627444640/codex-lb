# Verification — 2026-09-24

Source baseline: `a5836f109dac20efed9231653ab72fc5ce1abff6`. These checks cover the internal-distribution source changes; operational rollout is verified separately.

## Completed checks

- Backend telemetry/API-key/logging regression: 1,515 passed in the initial batch; its two settings-reference failures were subsequently resolved and the complete settings-reference file passed in the 52-test follow-up.
- Codex usage legacy monetary-limit regression: 121 passed.
- Trusted client-IP, auxiliary proxy routes and proxy-header middleware: 258 passed.
- Image/audio/model-source/token capture/warmup/planner regression: 415 passed in the initial batch; three new fixture setup errors were corrected. The corrected model-source tests, planner tests and full settings-reference file passed in the 52-test follow-up.
- Historical migration preservation guard plus migration runner: 69 passed, with eight existing SQLAlchemy expression-index reflection warnings. Direct raw historical migration was reproduced as destructive only on disposable synthetic data; the application runner rejected unsafe paths before any mutation.
- Frontend: 749 tests in 78 files passed, then 192 tests in 28 files passed; two integration files overlap, so these counts are not a unique total. Typecheck and ESLint passed.
- Ruff, formatting, Ty and proxy architecture checks passed.
- OpenSpec change strict validation passed. All 58 specs passed normal validation. Global strict validation retains 22 pre-existing Purpose-placeholder warnings; baseline validation has the same 22 failures and there are no new strict failures.
- Fresh isolated SQLite upgrade and schema drift check passed at the unchanged `20260921_000000_merge_local_timing_and_stale_recovery` head; repeated upgrade is safe. No historical migration file changed.
- Real browser smoke passed against a fresh temporary database and random loopback port. The sandbox blocked the existing GitHub version-check request; this did not affect the smoke result and is separate from anonymous telemetry.
- Fresh frontend and wheel builds passed. Wheel has no `app/modules/telemetry/`, collector URL, telemetry API path or telemetry UI keys. All 675 packaged app/config files matched the working source/build files.
- Candidate wheel was installed into a separate environment using pinned runtime dependencies, including AnyIO 4.15.1. With legacy telemetry enable set to true, packaged startup/health/readiness passed, routes remained unavailable, no identity was created, no HTTP attempt occurred, and schema drift was empty.
- Caddy client-IP candidate passed five actual isolated positive/negative cases. Production Caddy configuration was not changed or reloaded.

Counts above are per validation batch, with overlapping suites. Detailed validation captures and deployment artifacts are excluded from published source.

## Safety and limits

Backend tests and browser/package/Caddy rehearsals used isolated databases, keys, random test ports and SBPL restrictions against production state, production service ports and external network access. Frontend tests used MSW, at most two workers and disabled file parallelism; their attempt to lower priority was denied by the outer sandbox, so lowered scheduling priority is not claimed for those runs.

Production credentials, instance identifiers, request bodies and local operational records are excluded from public changes.

Production rollout, real authenticated model requests, actual LAN/Tunnel client-IP acceptance and full cloud CI/PostgreSQL/Docker/Helm matrices were not executed. A later rollout must retain the current telemetry-disabled environment for safe rollback, back up and drain before any single-instance restart/Caddy reload, and preserve data generated after the backup rather than restoring an old database over new traffic. Direct raw Alembic calls bypass the new application-runner historical-data guard and are not a supported shortcut.
