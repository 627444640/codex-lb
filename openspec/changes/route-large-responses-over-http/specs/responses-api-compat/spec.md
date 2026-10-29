## ADDED Requirements

### Requirement: Automatic transport avoids oversized upstream WebSockets

For streaming Codex/Responses proxy requests, the system MUST let operators
choose the upstream transport strategy through dashboard settings. In
automatic mode, a serialized Responses payload larger than the fixed 30 MiB
WebSocket safety budget MUST use upstream HTTP/SSE, including when the payload
contains inline or historical images. The automatic fallback MUST occur before
opening an upstream WebSocket. An explicit `websocket` transport selection MAY
override this automatic safety fallback.

#### Scenario: Large automatic payload uses HTTP upstream

- **WHEN** the resolved upstream transport strategy is `auto`
- **AND** the serialized Responses payload is larger than 30 MiB
- **THEN** the proxy uses upstream HTTP/SSE
- **AND** it does not open an upstream WebSocket for that request

#### Scenario: Large image payload uses HTTP upstream

- **WHEN** the resolved upstream transport strategy is `auto`
- **AND** the Responses input contains an `input_image` part
- **AND** the serialized payload is larger than 30 MiB
- **THEN** the proxy uses upstream HTTP/SSE

#### Scenario: Explicit WebSocket pin remains explicit

- **WHEN** the resolved upstream transport strategy is `websocket`
- **AND** the serialized payload is larger than 30 MiB
- **THEN** the proxy keeps the explicit upstream WebSocket transport selection
