## ADDED Requirements

### Requirement: Pricing evidence follows the active catalog

Validated active prices, bundled offline prices and code fallbacks MUST retain their existing precedence and perform no network I/O on the accounting path. New cache-write and modality rate fields MUST reject invalid, negative and non-finite values. Explicit tier-specific long-context prices MUST remain authoritative. Price evidence MUST identify the effective rate set, and a later catalog update MUST NOT relabel or recompute an existing persisted non-NULL amount.

#### Scenario: Dynamic catalog remains active
- **WHEN** a validated catalog installs an exact model with an explicit Priority long-context price
- **THEN** new requests use that price and preserve its effective pricing version
- **AND** previous non-NULL historical amounts remain unchanged

#### Scenario: Incomplete metadata does not invent prices
- **WHEN** a catalog lacks a service-tier price or required usage modality evidence
- **THEN** accounting does not fabricate a Standard-tier or host-model cost

#### Scenario: New rate fields are validated
- **WHEN** a cached snapshot contains a negative or non-finite cache-write or image rate
- **THEN** the snapshot is rejected without replacing valid active rates
