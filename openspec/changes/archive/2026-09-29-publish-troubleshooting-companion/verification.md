# Source publication verification — 2026-09-29

- Repository Ruff lint/format, `ty`, frontend ESLint/TypeScript and proxy architecture checks passed.
- Backend unit selection: **6,945 passed, 71 skipped**. Skips comprise 68 Helm-dependent cases (Helm unavailable) and three documented obsolete conflict scenarios.
- Frontend: **149 test files, 1,153 tests passed**.
- Status administration, troubleshooting and full model-source routing integration selection: **131 passed**.
- Portable companion: **60 Python tests and 9 JavaScript parser/DOM tests passed**, with temporary synthetic data and no real model call.
- OpenSpec: the publication change and all **59 main specifications** passed strict validation.
- Offline source-distribution and wheel builds passed; the source distribution includes the companion, while the wheel includes the dashboard/backend assets. Runtime directories and local-only release evidence are excluded. Bundled font license notices are retained.
- The complete `make ci` command was attempted but stopped at `bun install` because Bun is not installed on this host. Available jobs were run directly with the existing Node/Python environments. Docker/Helm infrastructure and the remaining full integration/E2E/PostgreSQL jobs are not claimed as passed. The shared development environment was not replaced or downgraded to run packaging.

## Scope and privacy review

The five previously unpublished base commits were reviewed along with the proposed source delta. Text scans found no private home paths, live credential patterns or host-specific addresses. The two newly reachable pre-existing UI screenshots were manually checked and contain clearly synthetic `example.invalid` fixtures. The companion source excludes runtime files, local reports, logs, databases, preview credentials and captured requests. Its initial gateway address is a labelled `example.invalid` placeholder; the running local guide data was not edited.

The source bundle and uncommitted files were preserved privately before branch creation. Publication targets only the feature branch and `v1.24.3`, using explicit refs without force or mirror pushes. This is a user-authorized local integration/publication, not a PR squash merge into `main`. The main-PR CodeRabbit/CI merge gates and release workflow are not being represented as completed.

Production installation, real Mercury generation, authorized-key diffusion timing and the incomplete dynamic browser/mobile acceptance remain separate from this source publication.
