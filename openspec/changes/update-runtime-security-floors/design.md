## Context

Docker check 122351995411 on PR #43 reports aiohttp 3.14.3, Brotli 1.2.0, certifi 2026.7.22 and urllib3 2.7.0. Fixed versions are 3.14.4, 1.2.1, 2026.10.18 and 2.8.0 respectively.

## Decisions

Raise only the affected direct dependency floors and resolve those four exact patched versions. aiohttp 3.14.4 requires `yarl>=1.25.1,<2.0`, so its mandatory transitive dependency also advances from 1.23.0 to 1.25.1. Other dependency versions stay fixed. uv normalizes the unchanged project prerelease version from `1.25.0-beta.9` to its PEP 440 spelling `1.25.0b9` in the lockfile. Retain TLS verification, timeouts, scanner severity and existing admission behavior.

Primary evidence:

- https://github.com/advisories/GHSA-2g87-pp6c-29x5
- https://github.com/advisories/GHSA-9v8h-qqgm-4m35
- https://github.com/advisories/GHSA-6q48-6c7w-9gw2
- https://github.com/urllib3/urllib3/releases/tag/2.8.0

The scan also lists CVE-2026-111064, CVE-2026-111066, CVE-2026-97687 and CVE-2026-97689. The fresh image gate remains the acceptance authority for the complete dependency graph.

## Risks / Trade-offs

Patched networking libraries can alter error/timeout handling. Run HTTP-client and proxy integration coverage before merge. Removing compromised trust roots can reject chains that previously validated; this is the intended security update and must not be bypassed by disabling certificate validation.

## Validation

The frozen environment resolves successfully and release metadata still validates as v1.25.0-beta.9. The HTTP-client/proxy-utility/transient-retry slice reports 1,490 passed and one Windows startup-probe timeout. Running that exact failure with the original five dependency versions reproduces the same timeout, so it is not introduced by the upgrade; it remains visible and is not skipped or weakened. Fresh Linux CI and the Docker image scan remain required.
