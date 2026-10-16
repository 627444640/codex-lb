# Verification notes

- The `openspec` CLI is not installed in this environment (`command not found`),
  so strict artifact validation could not run.
- Focused regression tests for the new matcher, quarantined injection guard,
  orphan custom-tool terminal path, operation-status-unknown retirement and
  request-log gates, history replay budgets, and existing forwarding header
  filters pass.
- `tests/unit/test_conversation_history_cache.py` (13),
  `tests/unit/test_http_bridge_anchor_loss_history_replay.py` (7), and the
  relevant bridge gate/recovery tests (5) pass. The full
  `tests/unit/test_proxy_http_bridge.py` run now passes all 743 tests after the
  settlement fixture supplies `prefer_earlier_reset_accounts=False` and the
  request-local health-handled guard prevents a duplicate penalty.
- Ruff check, Ruff format check, and `git diff --check` pass.
- No service restart, runtime configuration write, database write, or manual
  cleanup was performed.

