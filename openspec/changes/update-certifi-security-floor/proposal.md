## Why

The reviewed advisory GHSA-6q48-6c7w-9gw2 identifies compromised emSign certificate-chain trust in certifi versions before 2026.10.19. The combined baseline candidate's Docker security gate confirms the locked 2026.7.22 package is affected; the maintainer approved a separate minimal dependency fix without merging, deploying or modifying the installed production environment.

## What Changes

- Raise the certifi dependency floor to `>=2026.10.19` so fresh resolutions cannot choose the vulnerable release.
- Refresh the certifi locked release to 2026.10.19 and its public package artifact metadata, preserving unrelated package versions.
- Keep TLS verification and all Trivy security gates enabled; add no ignore entry or security exception.
- Validate the bundle in a disposable environment and rerun exact-head CI/security checks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is dependency security maintenance preserving existing verified-TLS behavior, not a new API, routing, schema or configuration contract. Specification deltas are explicitly skipped; the security rationale and verification are recorded here rather than inventing a new capability.

## Impact

Dependency manifest and lockfile plus this sanitized change record. No application source change, other dependency upgrade, version release, production installation, service restart or deployment.

Tracking: [security issue #38](https://github.com/627444640/codex-lb/issues/38), separate from [combined baseline validation #37](https://github.com/627444640/codex-lb/pull/37).

Advisory: https://github.com/advisories/GHSA-6q48-6c7w-9gw2
