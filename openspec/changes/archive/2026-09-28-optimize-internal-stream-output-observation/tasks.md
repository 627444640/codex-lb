## 1. Observation optimization

- [x] 1.1 Add conservative canonical-content recognition with parser fallback; verify differential empty/escaped/duplicate/nested/malformed cases.
- [x] 1.2 Integrate with the actual HTTP/SSE fast path; verify bounded full parses, unchanged bytes and reasoning-first sample evidence.

## 2. Validation and handoff

- [x] 2.1 Add/run a reproducible benchmark and record common-path and fallback costs without claiming end-to-end speed gains.
- [x] 2.2 Run affected proxy, timing, persistence and policy regressions; run Ruff, typing, architecture and strict OpenSpec checks.
- [x] 2.3 Verify/archive the completed feature, commit on feat, and document the later v1.24.3/status-page integration boundary.
