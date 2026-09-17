# TLS security-update compatibility evidence

The [TLS comparison requirement](spec.md#requirement-tls-extension-order-parity-is-calibrated-against-direct-traffic) compares invariant capabilities exactly. A security update is not a reason to ignore changed signature algorithms or label missing direct-client samples as a pass.

The 2026-09-17 rustls security update retains the measured hybrid-first group and key-share lists while adding ML-DSA signature IDs `[2308, 2309, 2310]`. This is an observable capability difference from the old provider. A sufficiently sampled old direct-client cohort compared with the new provider must therefore report that mismatch; randomized extension order and informational JA3 hashes cannot hide it.

The isolated library probe establishes only the listed before/after capabilities. Native transport fixtures and successful Ubuntu CI do not replace full direct-Codex TLS capture cohorts. The [archived change](../../changes/archive/2026-09-17-fix-rustls-handshake-boundary/context.md) explains the dependency boundary; its [verification record](../../changes/archive/2026-09-17-fix-rustls-handshake-boundary/verification.md) preserves local and cloud evidence.
