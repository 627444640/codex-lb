# Verification

## Source checks

- `python3 -m json.tool deploy/status-monitor/monitor/troubleshooting-seed.json`
- `deploy/status-monitor/.venv/bin/python -m unittest discover -s tests`
  — 58 tests passed.
- `NODE_PATH="/Users/a123/codex-lb/frontend/node_modules" node --test tests/test_faq_ui.cjs tests/test_status_ui.cjs tests/test_report_ui.cjs`
  — 12 tests passed.
- `git diff --check` passed.

## Runtime FAQ readback

Through the existing loopback monitor control API, the published guide was
created and read back with status `published`, revision `1`, and sort order
`55`. The public `/static/faq.html` readback contained both the Chinese guide
title and the `response protection is unavailable` signature. No gateway
database, account data or service process was modified or restarted.

## Validation limitation

The `openspec` CLI is not installed in this environment, so strict
`openspec validate --specs` and automated archive/verify commands could not be
run. The change artifacts and requirements were checked manually against the
status-page-management specification.
