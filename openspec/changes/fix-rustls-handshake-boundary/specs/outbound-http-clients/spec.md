## ADDED Requirements

### Requirement: Native TLS enforces handshake encryption boundaries

Native HTTP and WebSocket TLS clients MUST reject TLS 1.3 handshake messages sent across an encryption-level transition in an invalid record. Security dependency updates MUST retain native root certificate verification, TLS 1.2 support, hybrid-first key exchange, and the existing non-replayable TLS failure boundary.

#### Scenario: Peer combines messages across a TLS 1.3 key change

- **WHEN** a peer places a handshake message requiring the new encryption level in the same old-level record as a key-changing message
- **THEN** the native TLS handshake MUST fail instead of accepting the invalid transition
- **AND** the failure MUST NOT cause an ambiguously dispatched request to be replayed through another connector

#### Scenario: Security update retains hybrid key exchange

- **WHEN** the native TLS client emits its initial ClientHello after a security dependency update
- **THEN** its supported groups MUST keep X25519MLKEM768 first
- **AND** its initial key shares MUST retain hybrid and classical key exchange
- **AND** its certificate verification policy MUST remain enabled
