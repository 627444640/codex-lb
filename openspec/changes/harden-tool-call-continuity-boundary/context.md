# Context

The current production-shaped failure has two related symptoms. A durable
bridge retains an old response id and a pending custom tool-call manifest. The
bridge injects one synthetic output before reattaching, but upstream may no
longer have the matching tool-call item. The upstream then returns an orphan
output error, and the existing retry path can repeat the same injection.

The repair keeps the safety boundary explicit: a request must be protocol
correct and free of internal forwarding metadata, but it must not impersonate a
client or bypass upstream controls. If continuity ownership cannot be proven,
the service terminates the current session and asks the client for a new session
or complete context.

The same rule applies to the durable operation ledger. A row in `unknown` with
no upstream status proof is not evidence that a retry is safe: the current
bridge session is quarantined and retired, while the row and client-owned
anchor remain available for later operator or client recovery. The terminal
503 is recorded in request logs so admission failures are visible alongside
ordinary upstream failures.

Full-history replay also has a bounded admission gate. The default 128,000
extra-token ceiling is intentionally above the current ~64k replay evidence and
below the ~315k replay that preceded the loop; the serialized body must also
fit the existing upstream payload limit. This is a code default derived from
the incident evidence, not a live configuration write.

## Example

For a pending call `call_example` whose anchor is no longer valid, codex-lb may
observe a missing local output. It must not blindly prepend a
`custom_tool_call_output` and retry forever. It records the hashed mismatch,
returns the sanitized continuity error once, quarantines the bridge key, and
leaves a client-owned durable anchor untouched.

