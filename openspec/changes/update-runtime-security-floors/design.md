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

## Native dependency closure

The first fresh CI run passes the Python Docker scan but exposes ten native advisories (RUSTSEC-2026-0285, -0346, -0348, -0349, -0382, -0386, -0391, -0398, -0403 and -0410). Retain audit policy and protocol features; update rustls to 0.23.46, rustls-webpki to 0.103.16, Tokio to the patched 1.51.6 line, and zstd/zstd-safe/zstd-sys to 0.14.3/8.2.0/2.1.2. rustls requires aws-lc-rs 1.18, so pin 1.18.2 and resolve its companion sys crate. Updating async-compression and its codec/core dependencies also updates their Brotli allocator/decompressor closure. Preserve the pinned WebSocket fork revisions and Rust 1.96 toolchain.

Cargo 1.96.0 generated the lockfile using the official crates.io GitHub index as a temporary source replacement after the normal index endpoint timed out. The committed lockfile retains canonical crates.io source identities and checksums; no registry replacement configuration is committed. Native compilation, protocol tests and cargo-deny run in Linux CI; standalone Cargo metadata validation is not a substitute for those checks.

The first native-updated run passes the Rust build, 28 Rust test cases, 361 native wire-probe tests and cargo-deny. Its only unit failure is the existing packaging assertion still requiring the vulnerable rustls/aws-lc-rs versions. Update that assertion to the reviewed patched pins and retain its exact-version checks; the WebSocket fork and HTTP-family pins remain unchanged.

Primary native advisory references:

- https://rustsec.org/advisories/RUSTSEC-2026-0346.html
- https://rustsec.org/advisories/RUSTSEC-2026-0382.html
- https://rustsec.org/advisories/RUSTSEC-2026-0386.html
- https://raw.githubusercontent.com/RustSec/advisory-db/main/crates/zstd/RUSTSEC-2026-0391.md
- https://rustsec.org/advisories/RUSTSEC-2026-0398.html
- https://rustsec.org/advisories/RUSTSEC-2026-0410.html
