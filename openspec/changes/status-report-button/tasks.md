## 1. Navigation

- [x] Add the published Lark form link after `常见问题` on the overview page.
- [x] Add the same link after `常见问题` on the FAQ page.
- [x] Add responsive highlighted navigation styling.

## 2. Validation

- [x] Add FAQ and overview DOM assertions for label, target and exact URL.
- [x] Run the monitor Python and browser UI tests.
- [x] Run JavaScript syntax checks and `git diff --check`.
- [x] Install only the changed static assets into the separate monitor runtime,
  preserving a rollback copy and keeping the real Lark URL out of source.
- [x] Read back the live overview and FAQ pages and verify the new link opens
  the Lark form in a new tab.
