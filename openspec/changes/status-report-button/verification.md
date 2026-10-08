# Verification

Source validation completed on 2026-10-08 (Asia/Taipei):

- `make test-status-monitor`: 43 Python tests passed, FAQ UI tests passed and
  status UI tests passed.
- `node --check` passed for `status.js` and `faq.js`.
- `git diff --check` passed.
- The Lark Base and form were created and read back through `lark-cli`; the
  public form share URL was obtained from the Lark form editor and validated
  with `+form-detail`.
- The separate monitor runtime received only the changed static assets, with a
  private rollback copy under `/Users/a123/Services/codex-lb/state/rollouts/`;
  the real form URL is runtime-only.
- Live FAQ and overview reads expose the button after `常见问题`, and the
  button opens the published Lark form in a new tab.
