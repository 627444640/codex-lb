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

## Example

For a pending call `call_example` whose anchor is no longer valid, codex-lb may
observe a missing local output. It must not blindly prepend a
`custom_tool_call_output` and retry forever. It records the hashed mismatch,
returns the sanitized continuity error once, quarantines the bridge key, and
leaves a client-owned durable anchor untouched.

