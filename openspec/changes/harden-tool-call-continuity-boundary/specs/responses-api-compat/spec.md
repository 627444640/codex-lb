# Delta specification: responses-api-compat

## Requirement: recognize orphan custom tool output errors

The service MUST classify an upstream `invalid_request_error` with
`param=input` and either an existing missing-output message or the phrase
`No tool call found for custom tool call output with call_id ...` as a tool-call
continuity error. It MUST rewrite the public error to the existing sanitized
retryable continuity envelope and MUST NOT expose the raw call id.

## Requirement: prevent repeated orphan-output injection

When an HTTP bridge session injects a synthetic tool output and upstream rejects
it because the matching tool call is absent, the service MUST clear the
session's in-memory pending-tool manifest, quarantine the session key, and
prevent another reconnect from injecting the same output. The service MUST NOT
cross accounts or clear a client-supplied durable anchor as part of this path.

## Requirement: protocol-only upstream headers

Upstream requests MUST exclude internal bridge-forwarding, proxy-chain,
reservation, owner, client-IP, and internal turn-metadata headers. Authentication
and client protocol fields MUST be rebuilt from their actual source; the service
MUST NOT forge source identity, TLS fingerprints, credentials, or client version.

## Requirement: continuity observability

The service MUST record a low-cardinality continuity decision for orphan tool
output rejection, including bridge-key hash, response-id hash, owner-proof
outcome, and quarantine decision. Raw call ids, request bodies, credentials, and
account secrets MUST NOT be recorded.

## Requirement: unknown operation is a terminal session outcome

When a durable bridge operation is already recorded but upstream status or
completion proof is unavailable, the service MUST fail the current request with
the existing `503 upstream_operation_status_unknown` envelope, quarantine and
retire the current bridge session, and prevent the same session key from
re-entering the operation through a reconnect. It MUST keep the durable
operation and any client-owned response anchor intact, and MUST NOT switch
accounts or submit a second opaque attempt.
The operation-status-unknown quarantine MUST NOT expire with the ordinary retry
circuit cooldown; only a verified completion path or bounded registry eviction
may clear the in-memory marker.

## Requirement: bridge admission 503s are request-log visible

When the retry circuit suppresses a bridge submission, or an unknown operation
is terminally rejected before upstream dispatch, the service MUST write a
request-log row containing the sanitized error code, failure phase, bridge
stage, upstream error code, and retry-after detail. The row MUST use the
request's existing identity and MUST NOT include raw operation or tool-call
identifiers.

## Requirement: history replay is budget-gated

Before recording or applying a full-history replay, the service MUST enforce a
bounded extra-token budget and a serialized request-body byte budget no larger
than the existing upstream `response.create` payload limit. When either budget
is exceeded, it MUST refuse the replay before incrementing replay counters or
marking transparent retry state, emit only redacted low-cardinality telemetry,
and continue through the existing fail-closed path. It MUST NOT silently slim
or dispatch an over-budget replay.

### Scenario: orphan custom tool output is sanitized once

- **GIVEN** an anchored HTTP bridge request injects a synthetic custom tool output
- **AND** upstream returns `invalid_request_error` with the orphan-output phrase
- **WHEN** the bridge processes the error
- **THEN** the client receives one sanitized `stream_incomplete` continuity error
- **AND** the session is quarantined
- **AND** the same synthetic output is not injected on the next reconnect

### Scenario: an existing missing-output phrase remains compatible

- **GIVEN** upstream returns `No tool output found for custom tool call call_...`
- **WHEN** the bridge processes the error
- **THEN** it follows the existing missing-tool-output continuity rewrite

### Scenario: client-owned anchor is not cleared

- **GIVEN** the rejected anchor was supplied by the client
- **WHEN** orphan tool output is detected
- **THEN** the service does not clear the durable response anchor
- **AND** it does not switch accounts or replay the request across accounts

### Scenario: unknown operation retires the bridge session

- **GIVEN** a durable operation already exists for the anchored request
- **AND** no upstream status or completion proof is available
- **WHEN** the bridge evaluates a reconnect or retry
- **THEN** it returns one `503 upstream_operation_status_unknown`
- **AND** quarantines and retires the current session
- **AND** writes a redacted gate request-log row
- **AND** does not dispatch a second opaque operation

### Scenario: replay budget rejects an oversized history

- **GIVEN** cached history would add more than the bounded replay token budget
  or exceed the upstream serialized request-body limit
- **WHEN** a continuity path plans a full-history replay
- **THEN** no replay is staged or counted
- **AND** the request follows the existing fail-closed error path
- **AND** no raw request body or identifiers are emitted in telemetry

