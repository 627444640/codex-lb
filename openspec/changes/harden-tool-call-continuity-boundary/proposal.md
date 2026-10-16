# Harden the HTTP bridge tool-call continuity boundary

## Summary

When an HTTP bridge reattaches to a durable `previous_response_id`, codex-lb may
retain a local pending tool-call manifest and inject a synthetic tool output.
If the upstream response context no longer contains the matching tool call, the
upstream rejects the request with an orphan-output `invalid_request_error` and
the bridge can repeat the same injection, history replay, and reconnect loop.

This change makes the boundary fail closed once, recognizes both upstream
missing-tool error phrasings, prevents repeated synthetic output injection after
an orphan-output rejection, and records the continuity decision without exposing
raw call ids or credentials. Upstream requests are rebuilt from a protocol
allowlist and MUST NOT carry internal forwarding metadata.

## Why

Production logs show repeated `http_bridge_interrupted_tool_outputs_injected`
events followed by `invalid_request_error` and reconnects for one durable
response. The local session has one pending custom tool call, while upstream no
longer recognizes the corresponding `custom_tool_call`. Existing matching only
recognizes “No tool output found ...” and misses “No tool call found for custom
tool call output with call_id ...”, leaving the retry path without the intended
continuity handling.

## Scope

- Add the new orphan-output error shape to the Responses compatibility contract.
- Mark a bridge session as quarantined after an orphan-output continuity mismatch
  and clear its in-memory pending tool-call manifest before any reconnect can
  inject the same output again.
- Keep client-supplied anchors and durable database state fenced; do not clear a
  client-owned anchor or cross accounts.
- Rebuild upstream headers from the existing filtered protocol surface and keep
  internal bridge-forwarding headers out of upstream requests.
- Add request/bridge telemetry and regression tests for matching, mismatch, and
  no-repeat behavior.
- Retire sessions that reach the durable-operation status-unknown terminal and
  make circuit-suppressed and operation-fenced 503s visible in request logs.
- Bound full-history replay by extra tokens and the existing upstream payload
  byte limit so a stale anchor cannot create an unbounded replay loop.

## Non-goals

- No service restart, configuration change, or manual database cleanup.
- No forged source IP, TLS fingerprint, authentication identity, user-agent, or
  anti-abuse bypass.
- No broad retry, queue, timeout, account-cap, or account-health changes.
- No cross-account replay for hard continuity.

## Capabilities

### Modified Capabilities

- `responses-api-compat`: strengthen tool-call continuity and upstream header
  boundaries.

