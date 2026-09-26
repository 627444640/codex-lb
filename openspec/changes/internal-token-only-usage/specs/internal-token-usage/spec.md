## ADDED Requirements

### Requirement: Internal usage remains token-only
The internal distribution MUST record input, output, cache-read, cache-write, and total token usage when available. It MUST NOT estimate a monetary cost for new requests or use model prices to admit, reject, reserve, or settle traffic. Missing prices MUST NOT reject otherwise valid traffic. Existing token limits and success/failure settlement semantics MUST remain enforced.

#### Scenario: Unknown-price model retains token accounting
- **WHEN** an otherwise valid request uses a model without a price
- **THEN** routing is not rejected for pricing availability and measured token usage is preserved
- **AND** the new request log stores `cost_usd=null` and `pricing_version=null`; no monetary estimate is calculated

### Requirement: Historical monetary records are preserved but inactive
Existing stored costs, model prices, monetary limit records and anonymous-telemetry columns MUST remain unchanged by removal or ordinary unrelated settings edits. Historical migrations MUST NOT be removed or reordered. New token-limit edits MUST preserve dormant monetary limits without enforcing them. Omitted model-price fields MUST NOT clear existing prices.

#### Scenario: Edit a token limit on a legacy key
- **GIVEN** a key has both token and historical monetary limits
- **WHEN** an administrator changes only token limits
- **THEN** token limits are updated and enforced while the old monetary records remain unchanged and inactive

### Requirement: Internal dashboard presents token usage without billing
The dashboard MUST expose token usage and operational request metrics without monetary totals, monetary charts, price editors, or monetary limit controls. Compatible legacy API fields MAY remain for historical reads but MUST NOT trigger price calculation or traffic accounting.

#### Scenario: Review usage and edit a model source
- **WHEN** an operator views usage or edits a model source without changing its models
- **THEN** token metrics remain visible and no price field is submitted or cleared

### Requirement: Historical migration imports cannot restore pricing

The historical migration graph MUST remain importable without changing or removing old revisions. Compatibility pricing entry points required by old migration imports MUST return `None` and MUST NOT contain rates or calculate monetary values.

#### Scenario: Fresh migration imports retired pricing names

- **WHEN** an unchanged historical migration imports `get_pricing_for_model` or `calculate_cost_from_usage`
- **THEN** the import succeeds and either function returns `None`
- **AND** no price table or monetary estimate is created

### Requirement: Upgrade runners preserve existing historical amounts

The application migration runner MUST refuse an upgrade before any schema, bootstrap, or revision writes when the pending path includes the retired request-cost backfill and existing request-log rows already contain non-null amounts, including zero. Fresh databases, null-only historical rows and databases already at the current head MUST retain supported startup behavior. No historical migration file SHALL be changed to implement this protection.

#### Scenario: An imported old database has already stored monetary history

- **GIVEN** the recorded revision predates the retired cost backfill and a request log already has a stored amount
- **WHEN** the application migration runner is asked to traverse that backfill
- **THEN** it fails with a clear compatibility error before mutation
- **AND** rows, schema and revision records remain unchanged
