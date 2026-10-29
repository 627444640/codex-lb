## MODIFIED Requirements

### Requirement: Upstream Responses event size budget

The service SHALL allow upstream Responses SSE events and upstream websocket
message frames up to 65 MiB before treating them as oversized. The budget is a
fixed application constant (`MAX_SSE_EVENT_BYTES` in
`app/core/clients/proxy.py`); it MUST NOT be operator-configurable, and the
serialized upstream `response.create` budget (64 MiB) MUST be derived from it
so the envelope can never exceed the frame ceiling.

#### Scenario: built-in tool output exceeds the old 2 MiB limit

- **WHEN** upstream Responses traffic includes a single SSE event or websocket
  message frame larger than 2 MiB but not larger than 65 MiB
- **THEN** the proxy continues processing the event instead of closing the
  upstream websocket locally with `1009 message too big`

#### Scenario: The effective response.create budget is 64 MiB

- **WHEN** a serialized `response.create` request is no larger than 64 MiB
- **THEN** the fixed upstream request guard does not reject it solely for size
- **AND** the shared upstream frame budget remains at least one MiB larger

#### Scenario: Oversized response.create remains fail-fast

- **WHEN** historical slimming cannot reduce a serialized `response.create`
  request to 64 MiB or less
- **THEN** the service retains the existing local `400 payload_too_large`
  behavior before opening or reusing an upstream websocket

#### Scenario: The event budget is not an environment setting

- **WHEN** the process starts with `CODEX_LB_MAX_SSE_EVENT_BYTES` or
  `CODEX_LB_UPSTREAM_RESPONSE_CREATE_MAX_BYTES` set
- **THEN** the values are ignored, startup logs the removed-setting warning
  once, and the 65 MiB / 64 MiB budgets apply
