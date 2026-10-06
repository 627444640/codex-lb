## MODIFIED Requirements

### Requirement: Public capacity uses an accessible energy meter

The seven-day capacity card SHALL render the weighted remaining percentage as
a dense segmented energy meter with 40 presentational blocks. The number of
filled blocks MUST equal the rounded percentage proportion after clamping to
0–100. Filled blocks SHALL be green at 60% and above, yellow from 20% up to
below 60%, and red below 20%.
The meter MUST retain progress-bar semantics and expose the exact numeric
percentage through `aria-valuenow` when known. Unknown capacity MUST render no
filled blocks and expose an unknown accessible value without changing the
underlying API contract.

#### Scenario: Known capacity renders energy blocks

- **WHEN** the public response contains a known seven-day percentage
- **THEN** the page renders 40 energy blocks
- **AND** the rounded percentage proportion is filled
- **AND** the meter exposes the percentage through its ARIA value

#### Scenario: Unknown capacity keeps the meter safe

- **WHEN** the public response has an unknown or stale capacity
- **THEN** all energy blocks are empty and muted
- **AND** the meter exposes `待核对` as its accessible value
- **AND** the page does not invent a percentage
