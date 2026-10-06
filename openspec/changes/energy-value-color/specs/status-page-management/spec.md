## MODIFIED Requirements

### Requirement: Weekly percentage shares the energy meter state

The large weekly capacity percentage SHALL use the same semantic color class
as the segmented energy meter. Values at or above 60% SHALL use the healthy
color, values from 20% through below 60% SHALL use the warning color, values
below 20% SHALL use the critical color, and unknown values SHALL use the muted
unknown color.

#### Scenario: Known percentage and meter agree

- **WHEN** the public response contains a known weekly percentage
- **THEN** the percentage and energy blocks have the same threshold class

#### Scenario: Unknown percentage remains neutral

- **WHEN** the weekly percentage is absent or stale
- **THEN** the percentage uses the unknown muted class
- **AND** the meter remains empty and muted
