## ADDED Requirements

### Requirement: Request costs retain pricing and usage evidence
Request logs MUST preserve the upstream input, output, cache-read, and reported cache-write token counts, actual response model, and pricing version. Cached and cache-write tokens MUST be treated as disjoint subsets of input, and reasoning tokens as a subset of output. Terminal failed responses that carry usage MUST retain that usage without changing the existing success-only quota settlement policy.

#### Scenario: Terminal failure contains usage
- **WHEN** a failed Responses event carries valid usage
- **THEN** the request log retains those tokens and the failure status

#### Scenario: Upstream selects a different model
- **WHEN** the response reports a model different from the requested model
- **THEN** the log preserves both identities and uses the actual model for its API cost estimate

### Requirement: Request cost precision and provenance
The request-log API and dashboard MUST preserve positive sub-cent costs. The dashboard MUST distinguish unknown prices, missing usage, incomplete usage, historical stored estimates, and current estimates. It MUST identify aggregate costs as sums of known estimates. Migration MUST preserve existing token counts and stored costs and leave newly unavailable metadata null; reading historical rows MUST NOT rewrite their persisted costs.

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
