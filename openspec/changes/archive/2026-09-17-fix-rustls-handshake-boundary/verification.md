# Verification — 2026-09-17

Base: main `d1fd2f21fa0e0f3b5fcad3af5fada19693cd1fc1`. Local environment: macOS ARM64, isolated Rust 1.96.0 and cargo-deny 0.20.2. No production operation was performed.

## Dependency and security evidence

- A rustls-only update failed: rustls 0.23.45 requires `aws-lc-rs ^1.18`, incompatible with the existing exact 1.16.2 pin.
- The successful candidate pins rustls 0.23.45 and aws-lc-rs 1.18.0. Only four lock package blocks change: rustls, aws-lc-rs, aws-lc-sys 0.39.1 → 0.44.0, and rustls-webpki 0.103.13 → 0.103.15. The sys crate adds a dependency on already-locked pkg-config; no other package is upgraded.
- Existing features, fork revisions, deny policy and CI workflow remain unchanged.
- `cargo deny --all-features check`: advisories, bans, licenses and sources all passed. The original RUSTSEC-2026-0285 no longer reproduces in the unchanged audit.
- Independent read-only review found no concrete surviving bypass or introduced regression. Its dependency tree confirmed one rustls instance serving native HTTP, HTTPS proxy and WebSocket paths.

## Build and normal transport checks

- `make rust-check`: formatting, Clippy with warnings denied, all 28 Rust tests, and release build passed.
- Native routed/SSE/WebSocket/usage probe files: 356 passed, 5 failed locally.
- The exact same five failures also reproduced with a separately built, unmodified main helper and original dependency lock. They are the direct public-idle-timeout error classification and the four post-head route-selection cases. No source/test workaround was applied.
- The unchanged Ubuntu native probe job subsequently passed all 361 tests on the immutable candidate below. This completes the native verification gate without changing the local tests; the same-machine baseline failures remain documented as a macOS limitation.
- `otool -L` on the new local release helper showed only macOS system frameworks/libraries, with no external crypto dylib. The new sys crate's system-AWS-LC probing is a custom-build environment boundary; other distribution targets still require their own checks.

## TLS capabilities

An isolated old/new ClientHello generator used each exact rustls/AWS-LC version pair and the project's unchanged provider/features. It emitted only parsed capability IDs in the persisted [evidence](evidence/tls-capabilities.json), without raw random bytes or key-share material.

- Supported groups are unchanged: `[4588, 29, 23, 24]`, with X25519MLKEM768 first.
- Initial key-share groups are unchanged: `[4588, 29]`, retaining hybrid and classical shares.
- Cipher suite IDs and order are unchanged.
- Signature algorithms add `[2308, 2309, 2310]` (ML-DSA 44/65/87). Complete ClientHello parity is therefore not claimed.

This controlled library probe is not a direct-Codex capture cohort or a complete real-network TLS/WSS handshake test. The strict comparison policy remains active and will report genuine capability differences. The upstream security patch was independently inspected, but no bespoke malicious TLS record replay was added to this repository.

## Other checks

- Strict OpenSpec change validation and git diff whitespace validation passed.
- Contributor attribution is a separate unchanged-gate prerequisite, copied from the already reviewed attribution patch.
- No commit, push, merge, deployment, audit exception or credential change was performed by this worker.

## Immutable cloud verification and archive assessment

[GitHub Actions run 35225366128](https://github.com/627444640/codex-lb/actions/runs/35225366128), [Rust workspace job 105215515209](https://github.com/627444640/codex-lb/actions/runs/35225366128/job/105215515209), completed successfully at 2026-09-17 13:14:26 UTC for commit `55c810d93dc3e4d58e8f5c8a058ff766c69956c3`. The job used the unchanged Ubuntu 24.04 workflow and fixed Rust 1.96.0 toolchain.

- Cloud formatting, Clippy, all 28 Rust tests and release build passed.
- Cloud native routed/SSE/WebSocket/usage probes: **361 passed, 1 warning in 25.25 seconds**.
- Cloud cargo-deny: advisories, bans, licenses and sources all passed.
- CI Required completed successfully on this same head.
- Working-tree `Cargo.toml` and `Cargo.lock` were compared byte-for-byte with this immutable commit before the documentation-only sync/archive; both matched. Their SHA256 values are respectively `2e366d16c1d08dbde1e8debad6c5766514c280d5153bb0f267b7636544ca3d12` and `f4702a0dce1830d4f5279185ad7fc33cdc3775af445065fbaf59d1a2a80f619c`.

Completeness: 6/6 tasks and both affected requirements are covered. Correctness: the patched dependency and audit close the reported encryption-level boundary, the capability probe retains group/keyshare invariants, and the analyzer retains exact signature comparison. Coherence: provider/features, replay boundaries and audit policy remain unchanged. No critical implementation or archival issue remains. The limits concerning bespoke malicious-record replay and full direct-Codex TLS parity above remain explicit.

This evidence validates the code at `55c810d9`; the later documentation commit still requires its own current-head CI/review/merge checks. Archival does not assert Ready or merge approval for a future head.

Post-archive checks: this archive validates successfully with all six tasks complete, both owning specifications pass strict validation, and git diff whitespace validation passes. The optional whole-history archived-task check reports 764 passed / 22 failed across 786 archives; each failing tasks.md is byte-for-byte unchanged from `55c810d9` and predates this change. No unrelated archived task was marked complete.
