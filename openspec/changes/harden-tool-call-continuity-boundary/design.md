# Design

## Decision: classify the upstream error before replay

The matcher accepts the existing missing-output forms and the observed orphan
output form:

```text
No tool output found for custom tool call call_...
No tool call found for custom tool call output with call_id call_...
```

Both require `code=invalid_request_error` and `param=input`. The raw call id is
never emitted in telemetry.

## Decision: prove tool ownership before synthetic injection

Synthetic `custom_tool_call_output` injection remains allowed only when the
local pending manifest is tied to the current anchored response and operation
owner. If the upstream rejects the output as orphaned, the current session is
quarantined, its in-memory pending-tool manifest is cleared, and the current
request is rewritten to the existing sanitized continuity failure. A reconnect
must not inject the same output again.

The durable anchor itself is not cleared by this path when it is client supplied.
Existing full-resend-gated, owner-epoch-fenced durable-anchor cleanup remains
the only path allowed to clear a proxy-injected anchor.

## Decision: upstream request surface

Upstream requests use the existing protocol filtering and reconstructed account
authentication. Internal bridge forwarding fields (`Via`, `X-Forwarded-*`,
`Cf-*`, bridge owner/reservation/signature fields, and turn metadata that is
only for internal routing) MUST NOT be forwarded upstream. No source identity,
TLS fingerprint, authentication credential, or client version is forged.

## Decision: observability

The bridge emits a low-cardinality continuity event containing the response-id
hash, bridge-key hash, owner-proof outcome, and quarantine decision. Request logs
use `failure_phase=continuity` and an internal orphan-tool error code while
redacting raw call ids and payloads.

## Failure modes

- Matching tool-call context: request continues through the existing path.
- Orphan tool output: one sanitized `stream_incomplete` terminal response and
  session quarantine; no repeated synthetic injection.
- Unknown owner/operation: fail closed without account switch or replay.
- Header-policy violation in tests: fail the validation gate before deployment.

