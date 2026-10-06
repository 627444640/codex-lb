# Verification

Source validation completed on 2026-10-06 (Asia/Taipei):

- `app-header.test.tsx`: 10 tests passed, including desktop and mobile
  Service status link placement, same-host `https://<host>:2467/` target,
  new-tab behavior and safe `noreferrer` relation.
- TypeScript application and Node configuration checks passed with `tsc`
  `--noEmit` in an isolated frontend copy.
- ESLint passed for the modified header component and test.
- A production Vite build passed in an isolated frontend copy and produced
  dashboard assets successfully.
- Locale JSON validation and `git diff --check` passed.

The dashboard build was not installed into the live Codex LB runtime because
the request asked for the navigation change but did not authorize a core LB
deployment or restart. The source is ready for the normal controlled
deployment procedure.
