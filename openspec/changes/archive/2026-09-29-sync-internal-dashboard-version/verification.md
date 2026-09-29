# Internal dashboard version verification — 2026-09-29

- `python -m scripts.verify_release_version`: all six release-managed version fields agree on `1.24.3`. This checks metadata only; no tag or public release was created.
- Focused backend tests: **45 passed** across release version helpers, runtime version service, version response middleware, and the runtime API contract.
- Focused frontend tests: **18 passed** across the status bar and i18n. Coverage includes runtime priority, Chinese `1.24.3内部版`, advancement to `1.24.4内部版`, the build-version fallback, and the existing update link.
- ESLint for the changed frontend component/tests, frontend TypeScript check, frontend production build, and Python init lint/format: passed.
- OpenSpec change and all **59** main specifications: strict validation passed.
- Isolated preview: authenticated `GET /api/runtime/version` returned `currentVersion: 1.24.3`; `X-App-Version` was `1.24.3`. The served entry and translation chunks matched the local build byte for byte and contained the dynamic internal label.

The browser reached the isolated preview's administrator login page. An authenticated visual screenshot was not completed; component tests and authenticated HTTP/build readback provide the verification above. Production installation, production restart, and full CI were not performed for this change. Bun is unavailable locally, so the installed frontend test, lint, typecheck, and build executables were run with Node.
