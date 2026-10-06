## MODIFIED Requirements

### Requirement: Public status distinguishes idle traffic from service failure

The independent public response and display SHALL keep the request component
unknown when no normal request samples exist, but SHALL NOT promote that idle
unknown component to the page-level degraded, outage or waiting-confirmation
status when the gateway, source collector and quota observations are
operational. The request section MUST state that business quality has no sample
and will be assessed after a real request. Existing request incident debounce
rules MUST remain unchanged.

#### Scenario: No normal requests while infrastructure is healthy

- **WHEN** the latest fresh snapshot has zero normal request samples
- **AND** gateway, source and quota components are operational
- **THEN** the page-level status is operational
- **AND** the request component remains unknown with an explicit no-sample
  explanation
- **AND** the banner explains that business quality is awaiting a real request

#### Scenario: Another component is unknown while traffic is idle

- **WHEN** there are no normal requests
- **AND** a gateway, source or quota component is unknown or unhealthy
- **THEN** the page-level status reflects that component state
- **AND** idle request traffic does not hide the component problem
