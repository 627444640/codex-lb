## Why

The main branch pins rustls 0.23.36, which cargo-deny rejects for RUSTSEC-2026-0285. Native HTTP and WebSocket egress must reject TLS 1.3 handshake messages crossing encryption-level boundaries while preserving the existing provider, hybrid key exchange and replay policy.

## What Changes

- Pin rustls 0.23.45 and its minimum compatible AWS-LC wrapper, 1.18.0; update only the necessary TLS dependency closure.
- Preserve all existing TLS features, native root handling and native/Python replay boundaries.
- Record the security fix and observable signature capability differences without claiming complete ClientHello parity from build tests alone.
- Retain exact invariant-profile comparison in the compatibility toolkit when an upgraded TLS provider advertises additional signature algorithms.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `outbound-http-clients`: Reject invalid TLS encryption-level transitions in native egress without weakening ordinary TLS or replay policy.
- `compatibility-tooling`: Explicitly preserve signature-capability mismatch evidence across security dependency upgrades.

## Impact

Cargo.toml, four TLS-related Cargo.lock entries, and OpenSpec evidence. No application API, database, credentials, workflow, audit exception or production deployment changes. Existing contributor attribution is carried separately to satisfy the repository's unchanged attribution gate.
