# Upstream Metadata Specification

## Purpose
The service SHALL maintain upstream pricing and Codex version metadata with offline fallbacks and repair retained missing request costs.
## Requirements
### Requirement: Automatic pricing metadata with offline fallbacks
The service SHALL refresh validated OpenAI text-token pricing from models.dev's public JSON, supplemented by compatible LiteLLM tier data at startup and periodically, without performing network I/O during cost calculation. It SHALL retain valid prices across partial updates and outages using a last-good persistent cache and a generated bundled snapshot before legacy code defaults. Invalid, negative, non-finite, incomplete, or non-OpenAI entries SHALL NOT replace valid prices. Exact models and their dated snapshots SHALL resolve before explicitly published compatibility aliases; arbitrary family-prefix matching SHALL NOT invent a model price. Unlisted GPT-5 minor families SHALL remain unpriced until recognized instead of inheriting the generic GPT-5 price. A newer bundled snapshot SHALL take precedence over an older persistent snapshot for overlapping models. Explicit Priority/Flex and long-context rates SHALL be honored when present, including complete tier-specific long-context rates without standard long-context rates. Every long-context rate group SHALL require a positive threshold. Runtime and code-generation catalog reads SHALL enforce a 16 MiB response limit before JSON parsing.

#### Scenario: New model and outage
- **WHEN** a refresh discovers GPT-6 Astra and a later refresh fails
- **THEN** subsequent requests continue using the validated Astra prices, including after restart

### Requirement: Safe missing-cost repair
The service SHALL automatically fill only NULL costs for retained subscription request logs with sufficient token usage and recognized pricing. It SHALL skip external model-source logs and preserve non-NULL costs, including zero. Repairs SHALL execute in bounded transactions under the fold-state lock and mirror the exact cost deltas into lifetime account/key, hourly usage, quarter-hour demand, and report aggregates according to their existing filters, deduplication, dimensions, and watermark boundaries. A partial index SHALL support the bounded eligible-row scan, and PostgreSQL SHALL build that index concurrently with recovery of invalid interrupted builds. Repeated execution SHALL NOT double-count costs or rewrite request counts, token counts, or admission/limit counters. Unexpected refresh and backfill failures SHALL defer retries independently for five minutes while allowing the other operation to proceed.

#### Scenario: Folded history
- **WHEN** a retained Astra request with NULL cost has already been folded
- **THEN** its raw cost and each affected aggregate gain the same correction atomically
- **AND** pruned history and already priced rows remain unchanged

### Requirement: Automated Codex fallback metadata
The service SHALL persist successful stable Codex release resolutions across restarts, reject prereleases, accept stable release tags when display names are unavailable, and back off failed remote lookups while serving the last-good version or configured fallback. A repository command and daily workflow SHALL refresh the bundled stable version and pricing snapshot from public upstream data, with reviewable changes and failure on invalid source data. The daily workflow SHALL regenerate the settings reference and expose repository write credentials only to its publishing step. Previously resolved versions SHALL NOT be downgraded by stale remote data, and persisted versions below the configured fallback SHALL NOT override it.

#### Scenario: Offline restart
- **WHEN** GitHub and npm are unavailable after a successful version resolution and restart
- **THEN** the service uses the persisted stable version without repeated immediate retries

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

#### Scenario: Partial refresh conflicts with complete accounting metadata
- **WHEN** a refresh changes a model's base rates but omits its previously known cache-write or modality rates
- **THEN** the last complete model record is retained
- **AND** old supplementary rates are not attached to incompatible new base rates

### Requirement: Known unpublished model prices remain unknown across refreshes

The built-in catalog pipeline MUST exclude the known unpublished price identifiers gpt-5.3, gpt-5.3-codex-spark and codex-auto-review from remote parsing, bundled snapshots and restored persistent caches. This exclusion MUST NOT disable explicitly validated prices for unrelated model identifiers or replace independently configured source prices.

#### Scenario: Old cached estimates cannot restore a guessed price
- **WHEN** a persistent snapshot or remote catalog includes one of the known unpublished identifiers
- **THEN** the identifier remains unpriced by built-in accounting
- **AND** other valid catalog entries remain available
