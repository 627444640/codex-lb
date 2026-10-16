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

