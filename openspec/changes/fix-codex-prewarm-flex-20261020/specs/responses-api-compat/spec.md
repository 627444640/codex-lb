## ADDED Requirements

### Requirement: Verified Codex no-generation prewarms tolerate unadvertised Flex

For direct Codex Responses WebSocket requests, the proxy MUST omit an explicit
Flex service tier only when the connection metadata identifies a prewarm,
the individual normalized response.create contains literal generate=false,
and the authoritative model registry knows the model and confirms that Flex
is not advertised. This normalization MUST occur before API-key usage
reservation, account selection and upstream serialization. A structured event
MUST record the model and original Flex tier without request contents or
credentials. Effective accounting, routing and request-log tier fields MUST
agree with the normalized default-tier request.

The proxy MUST preserve advertised Flex, unknown/non-authoritative catalog
state, unknown models and every non-Flex tier. Normal generation turns MUST
retain explicit service tiers, including later turns on a connection opened
for prewarm. A prewarm header without literal generate=false MUST NOT grant
this fallback. The existing account scope, model access and capability guards
MUST remain in force.

#### Scenario: Known model without Flex accepts a no-generation prewarm
- **GIVEN** an authoritative catalog advertises a model but not Flex
- **WHEN** a prewarm-marked WebSocket submits generate=false and service_tier=flex
- **THEN** selection and reservation use the effective default tier
- **AND** the upstream frame retains generate=false and omits service_tier
- **AND** the upstream prewarm completion reaches the client

#### Scenario: A generated follow-up keeps its explicit tier
- **GIVEN** a WebSocket connection opened with prewarm metadata
- **WHEN** a later frame requests generation with service_tier=flex
- **THEN** explicit Flex remains subject to the existing account catalog filter

#### Scenario: Supported or uncertain Flex is unchanged
- **WHEN** Flex is advertised, the catalog is non-authoritative, or the model is unknown
- **THEN** the prewarm retains Flex and existing selection behavior

#### Scenario: Other tiers remain access-controlled
- **WHEN** a no-generation prewarm explicitly requests priority or ultrafast
- **THEN** the proxy preserves that tier and its existing entitlement checks
