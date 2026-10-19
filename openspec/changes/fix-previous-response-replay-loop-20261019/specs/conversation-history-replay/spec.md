### Requirement: stale proxy-managed anchors are cleared before fail-closed replay

When an HTTP bridge request carries a proxy-injected `previous_response_id` and
upstream returns `previous_response_not_found`, the bridge MUST classify that
error before rewriting it to `stream_incomplete`, fenced-clear the matching
durable and live-session anchor, and then attempt at most one cached full-history
replay before emitting the fail-closed terminal.

The replay MUST omit `previous_response_id`, MUST preserve the complete cached
history, and MUST use the request's existing shared `replay_count` budget. If
the cache replay exceeds 128,000 extra tokens or 15 MiB, the bridge MUST fail
closed without truncating the input. Once model output is visible, the bridge
MUST NOT switch accounts or resend output.

#### Scenario: stale anchor recovery clears the injection source

- **GIVEN** a proxy-injected durable anchor has a complete cached history
- **WHEN** upstream returns `previous_response_not_found` before model output
- **THEN** the bridge clears the durable and live-session anchor
- **AND** sends one unanchored full-history replay
- **AND** records one consumed replay budget

#### Scenario: over-budget history remains fail-closed

- **GIVEN** the cached history exceeds the token or byte replay limit
- **WHEN** upstream returns `previous_response_not_found`
- **THEN** the bridge emits the existing fail-closed terminal
- **AND** sends no truncated history upstream
