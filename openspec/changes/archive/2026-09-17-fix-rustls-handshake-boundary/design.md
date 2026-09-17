## Context

See proposal.md. The affected native client uses the default AWS-LC provider for HTTP and WebSocket TLS. Its manifest intentionally enables `prefer-post-quantum` and `tls12`; native certificate roots and replay boundaries are independent application contracts.

## Goals / Non-Goals

Goals: remove the vulnerable TLS implementation, retain the hybrid-first key exchange design, and expose any changed signature capabilities honestly.

Non-goals: emulate an old vulnerable TLS fingerprint, change certificate verification, switch crypto providers, relax the audit policy, or deploy a service.

## Decisions

- Use rustls 0.23.45, the first patched release named by RustSec. A rustls-only update was attempted and Cargo rejected its `aws-lc-rs ^1.18` requirement against the project's exact 1.16.2 pin.
- Update the wrapper pin to the minimum compatible 1.18.0. Cargo resolves its required sys crate and rustls's required webpki version; all unrelated lock entries remain unchanged.
- Keep the original feature lists and fork revisions. Do not suppress new signature capabilities or remove post-quantum key exchange to imitate an old ClientHello.
- Retain the existing exact invariant-profile comparison. A security update changing signature capabilities must remain visible as a mismatch; normal HTTP/WS probes are not evidence of full parity.

## Risks / Trade-offs

- Newer AWS-LC defaults advertise ML-DSA verification schemes. Validate the actual group/keyshare lists and report signature differences; do not claim byte-for-byte ClientHello equality.
- macOS local verification does not replace Ubuntu CI. Run the unchanged Rust and native probe jobs on the immutable PR head.

## Migration Plan

No database or user configuration migration. Build and audit the fixed dependency graph, then use the ordinary release workflow. Production deployment is outside this change. A rollback must not reintroduce the known vulnerable rustls range.
