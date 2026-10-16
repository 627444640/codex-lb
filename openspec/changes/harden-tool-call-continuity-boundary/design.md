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

## Decision: operation status unknown is terminal for the current session

An existing durable operation without upstream status proof is treated as an
ambiguous dispatch. The bridge keeps its SQLite fence and client-owned anchor,
then quarantines and retires only the current in-memory session before
returning `503 upstream_operation_status_unknown`. This prevents the
half-open/reconnect loop without pretending that the upstream operation failed.
The same branch writes a request-log row with low-cardinality phase, stage, and
retry-after detail. Its in-memory quarantine marker is terminal for that key
instead of sharing the ordinary 600-second wedge TTL, so the same unknown
operation cannot reappear on the next half-open interval; the bounded registry
still provides an eviction limit.

## Decision: replay budget uses existing payload policy

History replay is admitted only when the added history is at most 128,000
estimated tokens and the serialized request body is within the existing
`upstream_response_create_max_bytes` limit (15 MiB by default). These limits
allow the observed ~64k-token recovery while rejecting the ~315k-token replay
that repeatedly preceded the 502/503 loop. A rejected replay is left
unmarked, so the caller takes its existing fail-closed path rather than
silently shrinking or re-dispatching the payload.

## Failure modes

- Matching tool-call context: request continues through the existing path.
- Orphan tool output: one sanitized `stream_incomplete` terminal response and
  session quarantine; no repeated synthetic injection.
- Unknown owner/operation: fail closed without account switch or replay.
- Header-policy violation in tests: fail the validation gate before deployment.

