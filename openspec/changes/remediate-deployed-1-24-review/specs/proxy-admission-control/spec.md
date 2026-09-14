## ADDED Requirements

### Requirement: Memory admission uses current resident memory

Memory-based admission MUST use a current resident-memory measurement and MUST NOT use a process lifetime high-water mark. On macOS without psutil the service MUST read the current resident size through the native task API. When memory falls below the rejection threshold, otherwise admissible requests MUST be accepted again without restarting the process. If no current-memory provider is available, the existing one-time diagnostic and disabled-check behavior SHALL apply rather than substituting peak memory.

#### Scenario: Memory recovers after a temporary peak

- **WHEN** current resident memory rises above the rejection threshold and later falls below it
- **THEN** admission rejects requests while memory is high
- **AND** accepts requests after memory is released without requiring a restart

#### Scenario: A current-memory provider fails

- **WHEN** the platform cannot provide a current resident-memory measurement
- **THEN** the service emits its provider-unavailable diagnostic
- **AND** does not use ru_maxrss to make a permanent rejection decision
