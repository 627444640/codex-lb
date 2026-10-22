## Context

The reviewed GHSA-6q48-6c7w-9gw2 advisory and exact-head Docker scan identify certifi 2026.7.22 as vulnerable. PyPI lists the non-yanked 2026.10.19 release with no additional dependencies. The maintainer authorized this isolated dependency update while keeping all PRs unmerged and production untouched.

## Goals / Non-Goals

**Goals:** require and lock the first recommended patched release, verify public artifact metadata and the CA bundle, and preserve the real security gate.

**Non-goals:** change TLS verification policy, alter proxy routing, disable scans, upgrade unrelated packages, change application/schema/settings, release a version, install into production, restart services or deploy.

## Decisions

1. Raise the manifest floor to >=2026.10.19 and lock 2026.10.19. The floor protects installations that resolve without the committed lock; the lock gives reproducible CI and image builds.
2. Resolve only certifi against the existing public index. Reject a lock diff that changes unrelated package versions or records private/authenticated artifact URLs.
3. Check the lock's certifi wheel/sdist SHA256 values against published PyPI metadata. Use a disposable environment for a bundle-loading smoke check rather than modifying the installed production environment.
4. Keep all scanner severities, exit-code behavior and TLS hostname/certificate verification unchanged. Exact-head Docker/Trivy results, not a changed ignore list, determine remediation.
5. Record this maintenance change with skip_specs=true because no existing API/routing contract is being changed. Security rationale is here; no speculative capability is introduced.

## Risks / Trade-offs

- Removing a compromised trust anchor from certifi intentionally removes that bundled trust path. The recommended 2026.10.19 release restores unaffected emSign roots; do not hand-edit the CA bundle. Existing clients can additionally load OS/default roots, so this package-level check does not prove removal from every live trust store and does not authorize OS certificate-store changes.
- Local project regression environments may contain the previous installed dependency. Report isolated patched-bundle results separately; rely on CI that installs the new lock for the full updated-dependency run.
- A successful dependency update does not resolve the separately recorded HTTP 400/422 contract discrepancy or local combined-TestClient lifecycle investigation.

## Verification and rollback boundary

Check manifest/lock consistency, unchanged unrelated package inventory, artifact hashes and TLS context construction with the patched bundle. Publish a separate Draft PR based on the combined baseline candidate, then inspect current-head CI including the high-severity Trivy gate. No merge, production package install or rollback action is performed in this task.
