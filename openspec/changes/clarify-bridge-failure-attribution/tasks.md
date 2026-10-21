## 1. Characterization and privacy baseline

- [x] 1.1 Inspect owning main specs, active deltas and existing gate/recovery tests; document the unchanged invariants and synthetic-only publication scope in design/context and GitHub #16.
- [x] 1.2 Run the existing retry-circuit, generation-claim, same-attempt and anchor-poison regression subset; record the exact command and outcome locally and a sanitized summary in context.
- [x] 1.3 Add a focused synthetic gate-characterization test module covering expired cooldown with occupied half-open probe, allowance-flag asymmetry, concurrent probe admission, restored durable state and lookup failure; verify it passes against the baseline.

## 2. Typed gate decisions and error mapping

- [x] 2.1 Extract one typed authoritative admission result and preserve the boolean wrapper; verify exact boolean compatibility, one evaluation/claim per request and unchanged allowance rules.
- [x] 2.2 Distinguish generation claim conflict from missing proof or unavailable persistence without changing CAS or operation fences; verify existing and focused concurrency/claim-failure tests.
- [x] 2.3 Surface genuine future cooldown as bridge_session_cooldown with truthful Retry-After, and distinguish other gate refusals; verify startup and already-started SSE behavior without additional dispatch.
- [x] 2.4 Audit and update affected startup/stream recovery allowlists, owner-forward propagation and log classification; verify the new local gate code is not treated as ambiguous upstream execution.
- [x] 2.5 Add or preserve per-attempt/sibling attribution regression coverage; modify production attribution only if a test demonstrates a defect, and verify UNKNOWN/ACKNOWLEDGED evidence and dead-anchor cleanup remain intact.

## 3. Verification and publication

- [ ] 3.1 Run focused unit and HTTP bridge route regressions, then relevant broader suites; record exact results and any baseline failures, not merely HTTP 200 counts.
- [ ] 3.2 Run Ruff/format, type checking and strict OpenSpec validation for the change and owning specifications; do not substitute manual inspection for validation.
- [ ] 3.3 Audit the staged diff and every newly published ancestor for privacy; verify only reviewed source/tests/sanitized OpenSpec are publication candidates and keep raw logs local.
- [ ] 3.4 Publish a focused PR linked to #16 and #15 using the repository template; preserve existing release PR #1, record CI/review state, and do not merge or deploy without the corresponding gates.
