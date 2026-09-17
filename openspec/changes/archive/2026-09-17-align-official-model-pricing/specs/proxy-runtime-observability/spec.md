## MODIFIED Requirements

### Requirement: Request cost precision and provenance
The request-log API and dashboard MUST preserve positive sub-cent costs. The dashboard MUST distinguish unknown models, unknown service-tier or context prices, missing usage, incomplete usage, historical stored estimates, and current estimates. A known model with complete usage but no verified tier/context price MUST have null cost and the `unknown_pricing` status. It MUST identify aggregate costs as sums of known estimates. Migration MUST preserve existing token counts and stored costs and leave newly unavailable metadata null; reading historical rows MUST NOT rewrite their persisted costs.

#### Scenario: Positive sub-cent cost
- **WHEN** a request costs 0.00061288 USD
- **THEN** its displayed amount is positive and is not rounded to 0.00 USD

#### Scenario: Unknown public model
- **WHEN** no verified pricing exists for a model and no stored estimate is available
- **THEN** its cost is unknown rather than zero or a guessed alias price

#### Scenario: Historical rate changes
- **WHEN** a historical row contains an estimate calculated before the current pricing version
- **THEN** the stored amount is retained and identified as historical

#### Scenario: Cache writes were not reported
- **WHEN** a model charges separately for cache writes and the upstream omits that count
- **THEN** an available base estimate is identified as incomplete

#### Scenario: Tier has no public rate
- **WHEN** Sol reports complete usage on ultrafast without a stored estimate
- **THEN** the request-log API returns null cost and unknown_pricing
- **AND** the dashboard labels the price as unknown
