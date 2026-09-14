## ADDED Requirements

### Requirement: Zstd allocations are bounded before decoding

The service MUST reject a zstd frame whose declared decoded size exceeds the route's decoded-body budget before allocating the declared output. Zstd decoding MUST bound both emitted output and decoder window memory. The decoder window budget SHALL be the greater of the route budget and the format's minimum 1 KiB window. Frames without a declared decoded size MUST receive the same bounded decoding. Budget failures MUST use the existing HTTP 413 path-family envelope. Supported under-budget single frames and stacked encodings MUST retain their existing behavior.

#### Scenario: Known decoded size exceeds the budget

- **WHEN** a small zstd request declares decoded output larger than the route budget
- **THEN** ingress rejects it with HTTP 413 without allocating the declared output

#### Scenario: Unknown decoded size expands beyond the budget

- **WHEN** a zstd frame without a declared content size expands beyond the route budget
- **THEN** decoding stops within the bounded output buffer and ingress returns HTTP 413

#### Scenario: Decoder window exceeds the budget

- **WHEN** a small zstd frame declares a decoder window larger than the permitted window budget
- **THEN** ingress rejects it with HTTP 413 before the decoder allocates that window

#### Scenario: Supported first-frame handling remains compatible

- **WHEN** an under-budget zstd first frame is followed by another frame or trailing bytes
- **THEN** the service preserves its existing first-frame decoding behavior
- **AND** subsequent bytes cannot cause an additional unbounded decode

#### Scenario: A small frame uses a large configured budget

- **WHEN** a valid small zstd frame arrives with a configured body budget greater than the native window-parameter range
- **THEN** the service uses the frame's validated window requirement for the native decoder
- **AND** accepts the request without passing the larger body budget as an invalid native parameter
