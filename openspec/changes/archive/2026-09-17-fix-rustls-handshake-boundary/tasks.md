## 1. Minimal dependency repair

- [x] 1.1 Pin the first patched rustls release and minimum compatible AWS-LC wrapper; verify Cargo resolves only the necessary TLS dependency closure.
- [x] 1.2 Preserve all existing features, fork revisions and audit policy; verify the focused manifest/lock diff and cargo-deny result.

## 2. Compatibility verification

- [x] 2.1 Run Rust formatting, Clippy, workspace tests and release build with the pinned toolchain; record command results.
- [x] 2.2 Run the existing native routed, SSE, WebSocket and usage probes against the built helper; record transport verification limits.
- [x] 2.3 Compare old/new provider ClientHello groups, key shares and signature algorithms; record retained invariants and any capability difference.
- [x] 2.4 Independently review the exact patch, validate OpenSpec and record final local/cloud verification boundaries before archival.
