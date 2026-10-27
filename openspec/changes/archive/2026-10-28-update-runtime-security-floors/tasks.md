## 1. Dependency maintenance

- [x] 1.1 Read the failing image scan and verify the fixed versions against primary advisories/releases.
- [x] 1.2 Update the affected floors/locked versions and aiohttp's required yarl dependency; verify the lockfile diff.
- [x] 1.3 Run HTTP-client/proxy compatibility checks with the patched packages and reproduce the single Windows timing failure on the original dependency versions.
- [x] 1.4 Resolve native TLS, Tokio and compression advisory findings with compatible patched pins and a generated canonical lockfile.

## 2. Acceptance

- [x] 2.1 Validate the maintenance change and frozen dependency environment.
- [x] 2.2 Require current-head CI including the fresh Docker vulnerability scan before merge.
