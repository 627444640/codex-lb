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
- The native probe task remains incomplete until the immutable candidate passes the unchanged Ubuntu CI job. The local baseline comparison prevents treating these failures as evidence unique to the dependency update; it does not claim a platform fix.
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
