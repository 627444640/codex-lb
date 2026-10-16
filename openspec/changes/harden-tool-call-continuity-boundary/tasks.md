## 1. Spec and contracts

- [x] 1.1 Add the delta requirements and scenarios for orphan custom tool output, no-repeat quarantine, protocol-only upstream headers, and redacted continuity telemetry.
- [x] 1.2 Add design/context decisions and explicitly document client-owned anchor and no-identity-forgery boundaries.

## 2. Implementation

- [x] 2.1 Recognize the observed `No tool call found for custom tool call output with call_id ...` error shape while preserving input-parameter and error-code gates.
- [x] 2.2 Add a session-scoped orphan-tool context quarantine and clear the in-memory pending-tool manifest before reconnect/retry can inject the same output.
- [x] 2.3 Preserve the existing fenced durable-anchor rules: never clear a client-supplied anchor or cross accounts.
- [x] 2.4 Verify and enforce the upstream protocol-header allowlist at the HTTP bridge boundary; existing forwarding filters and tests cover internal metadata removal.
- [x] 2.5 Emit redacted continuity decision telemetry for the orphan-tool terminal path.
- [x] 2.6 Bind the in-memory pending-tool manifest to the response ID that produced it and reject injection when the manifest and current anchor differ.
- [x] 2.7 Retire and quarantine the current session when an existing durable operation has no upstream status proof, preserving the durable fence and client-owned anchor.
- [x] 2.8 Write request-log metadata for retry-circuit-suppressed and operation-status-unknown 503 gate outcomes.
- [x] 2.9 Add bounded token and serialized-byte admission checks before history replay.
- [x] 2.10 Make precreated account-health handling idempotent when terminal bookkeeping revisits a handled request.

## 3. Tests

- [x] 3.1 Extend missing-tool-output matcher tests with the orphan-output wording and unrelated invalid-request negatives.
- [x] 3.2 Add HTTP bridge coverage proving one orphan-output terminal response, session quarantine, and no repeated synthetic injection.
- [x] 3.3 Add tests for client-owned anchors, proxy-injected anchors, owner mismatch, and no account switch (existing continuity tests retained; new quarantine path is session-local).
- [x] 3.4 Use existing outbound-header tests proving internal forwarding headers are absent and required protocol/auth fields remain present.
- [x] 3.5 Run focused unit tests and Ruff checks available in this environment.
- [x] 3.6 Add a regression proving a pending-tool manifest from an older response cannot be injected into a newer anchor.
- [x] 3.7 Test the operation-status-unknown terminal state and redacted gate request log.
- [x] 3.8 Test request-log metadata for retry-circuit suppression.
- [x] 3.9 Test token and serialized-byte replay budget rejection without replay accounting.
- [x] 3.10 Keep the settlement-ordering regression green with a handled request and one deferred health penalty.

## 4. Verification and release preparation

- [ ] 4.1 Validate OpenSpec artifacts; the `openspec` CLI is unavailable in this environment and strict validation remains pending (recorded in `notes.md`).
- [x] 4.2 Review runtime/source differences and record that a later canary must align installed runtime identity.
- [x] 4.3 Keep deployment, restart, configuration, and database cleanup out of this change execution.

