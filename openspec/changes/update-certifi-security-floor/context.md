# Context

## Purpose and authorization

Independent remediation of GHSA-6q48-6c7w-9gw2, tracked in issue #38. The maintainer approved updating certifi in a separate Draft PR, with no merge, deployment or modification to the installed production environment.

## Evidence

- Advisory: https://github.com/advisories/GHSA-6q48-6c7w-9gw2
- Patched release metadata: https://pypi.org/pypi/certifi/2026.10.19/json
- The advisory's affected range ends before 2026.10.19; it recommends that release or later. The locked package was 2026.7.22.
- The current Docker scan reports this exact package/advisory; no unrelated application failure is being classified as a dependency issue.

## Design rationale

A minimum safe manifest version and an exact regenerated lock provide both safe future resolution and reproducible builds. Public PyPI artifacts are verified against their published digests. The CA bundle is loaded unchanged; TLS verification and the security scan remain enabled.

## Example and failure modes

A fresh resolver honoring the manifest cannot select the previously vulnerable certifi version. A build honoring the lock uses the patched artifact. A scan that still reports the advisory remains a failure; no ignore entry or weakened severity policy is an acceptable substitute.

## Privacy and deployment constraints

Only dependency manifests and sanitized OpenSpec records are published. Test environments and caches stay in ignored local directories. No database, credential, production log, user payload, local configuration, server restart or installed-production-package change is part of the patch.

## Verification record

- Parsed manifest/lock comparison: 140 locked packages; only certifi's release/artifacts and the project's certifi requirement changed. Unrelated package entries and lock options are identical.
- Wheel and sdist SHA256 values match the official PyPI release metadata; `uv lock --check --offline` passed.
- Disposable Python environment: certifi 2026.10.19, 120 loaded CA certificates, affected `emSign ECC Root CA - G3` absent from that bundle; certificate and hostname verification remain enabled.
- Client regressions explicitly loading the isolated patched package: 50 passed. The existing development environment and installed production environment were not upgraded.
- Local wheel build succeeded; METADATA requires `certifi>=2026.10.19`. Its 695 entries contain only application/configuration/distribution-metadata roots, not local caches, evidence or database artifacts. The wheel remains local and is not a publication candidate.
- Strict OpenSpec maintenance validation and whitespace checks passed. Independent read-only review found no patch blocker.
- Exact-head CI and high-severity Trivy verification remain pending until publication. No merge, deployment, service restart or live upstream probe was performed.

The root-absence check applies to certifi's bundle, not every OS/default trust store. Existing transports can combine default roots with certifi; this dependency-only patch does not inspect or modify the system certificate store.
