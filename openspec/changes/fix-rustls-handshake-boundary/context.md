# Rustls encryption-boundary repair — 2026-09-17

## Purpose and source

The original Rust CI job passed compilation, tests and native route probes but failed its unchanged RustSec audit for rustls 0.23.36. [RUSTSEC-2026-0285](https://rustsec.org/advisories/RUSTSEC-2026-0285.html) identifies 0.23.45 as patched. The upstream handshake transcript remains authenticated; this change does not claim a broader handshake-forgery vulnerability.

## Dependency boundary

The workspace pin affects reqwest/hyper-rustls HTTP, tokio-rustls proxy TLS and tokio-tungstenite WebSockets. Upstream [0.23.45 dependencies](https://raw.githubusercontent.com/rustls/rustls/v/0.23.45/Cargo.toml) require AWS-LC wrapper ^1.18 and webpki ^0.103.14. The first rustls-only Cargo attempt failed against the exact 1.16.2 wrapper pin, so the minimum compatible wrapper pin is included.

## Compatibility constraint

The crate README promises X25519MLKEM768-first groups and hybrid/classical key shares. No application source customizes the signature algorithm list. Upstream [0.23.44](https://github.com/rustls/rustls/releases/tag/v%2F0.23.44) added ML-DSA to default AWS-LC verification schemes; a signature capability change is observable and must not be presented as complete ClientHello parity. Existing strict capability comparison remains unchanged.

## Example and failure behavior

A plaintext EncryptedExtensions message packed after ServerHello in an old-level record must now fail the handshake. A correctly encrypted connection continues through the existing native transport. HTTP/WS fixture tests validate transport and cleanup behavior; they do not constitute direct-Codex TLS parity evidence.

## Operational scope

This is an isolated main-based prerequisite patch. No credentials, deployment wrapper, production process, audit exceptions or workflow definitions are changed. Final evidence records the exact lock closure and distinguishes local macOS checks from cloud Ubuntu checks.

## Measured capability result

The controlled old/new ClientHello probe retained supported groups `[4588, 29, 23, 24]`, key-share groups `[4588, 29]`, and cipher suite order. The patched provider adds signature IDs `[2308, 2309, 2310]` (ML-DSA 44/65/87). These are observed capability differences, not a full direct-Codex parity claim. See verification.md for the local/native-platform boundaries.
