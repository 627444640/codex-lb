## ADDED Requirements

### Requirement: Internal API keys enforce token limits without monetary billing

The internal distribution MUST retain token-based authentication, model restrictions, admission, reservations, and settlement. It MUST NOT calculate monetary costs or consult prices for these decisions. New request logs MUST store `cost_usd=null` and `pricing_version=null`. A missing price MUST NOT reject otherwise valid traffic. Compatible historical monetary values MAY remain readable without repricing.

#### Scenario: An unpriced model is governed by token limits

- **WHEN** an authenticated permitted request uses a model or tier without a price
- **THEN** admission and settlement use the applicable token limits
- **AND** no pricing-availability error or monetary estimate is generated

#### Scenario: Historical amounts remain unchanged

- **GIVEN** a stored request contains a non-null historical cost and pricing version
- **WHEN** usage or request-log APIs read it
- **THEN** the existing values remain unchanged
- **AND** no current price table is consulted or applied

### Requirement: API key token accounting preserves service-tier metadata

Requested, actual and effective service tiers MUST remain request metadata. Token accounting MUST settle actual usage independently of model or service-tier prices.

#### Scenario: Requested and actual tiers differ

- **WHEN** a request asks for `priority` and upstream reports `default`
- **THEN** both tier values remain available in the request log
- **AND** token settlement uses reported usage without computing a currency value

### Requirement: Monetary limit records remain inactive and preserved

The system MUST reject key creation or submitted rule updates containing `cost_usd` or `credits` with HTTP 400 before committing changes. It MUST NOT invent a currency or credit conversion. Existing monetary rules MUST remain inactive: they MUST NOT block authentication, admission or token settlement, and their counters and reset times MUST NOT be changed by normal traffic, resets of token usage or token-only limit edits. The dashboard MUST expose only token-limit controls. Account-level upstream quota and reset-credit functionality MUST retain its independent behavior.

#### Scenario: Reject unsupported rules atomically

- **WHEN** an administrator creates a key or submits `cost_usd` or `credits` in a limit update
- **THEN** the endpoint returns HTTP 400 with a token-only limit explanation
- **AND** no key or limit changes are committed

#### Scenario: Exhausted historical monetary rules do not block token capacity

- **GIVEN** a key has an exhausted or expired monetary rule and available token capacity
- **WHEN** a valid permitted request is received
- **THEN** only active token limits govern admission and settlement
- **AND** the monetary rule remains unchanged

#### Scenario: Token edits retain dormant monetary rows

- **GIVEN** a key has token and monetary rules
- **WHEN** an administrator updates only token rules or resets token usage
- **THEN** token rules are updated as requested
- **AND** omitted monetary rows retain their IDs, values and reset times without becoming active

#### Scenario: Upstream quota remains distinct

- **WHEN** a token-limited key reads its usage
- **THEN** token limits retain their units and source
- **AND** upstream quota or reset-credit data is not treated as a local monetary rule

## MODIFIED Requirements

### Requirement: API Key update
The system SHALL allow updating key properties via `PATCH /api/api-keys/{id}`. Updatable fields: `name`, `allowedModels`, `weeklyTokenLimit`, `expiresAt`, `isActive`, `usageSections`, `transportPolicyOverride`. The key hash and prefix MUST NOT be modifiable. The system MUST accept timezone-aware ISO 8601 datetimes for `expiresAt` and normalize them to UTC naive before persistence. The `transportPolicyOverride` field MUST accept `null` (follow the global policy) or one of `"smart"`, `"always_http"`, `"always_websocket"`; any other value MUST be rejected with HTTP 400.

When a submitted token limit rule does not match an existing token rule by `limit_type`, `limit_window`, and `model_filter`, the system MUST initialize the new rule's `current_value` from the API key's successful existing request-log usage in that rule's current window. If `resetUsage` is true, the system MUST initialize submitted token limits with `current_value: 0`, while preserving dormant monetary limits.

#### Scenario: Update key with timezone-aware expiration
- **WHEN** admin submits `PATCH /api/api-keys/{id}` with `{ "expiresAt": "2025-12-31T00:00:00Z" }`
- **THEN** the system persists the expiration successfully without PostgreSQL datetime binding errors
- **AND** the response returns `expiresAt` representing the same UTC instant

#### Scenario: Update non-existent key

- **WHEN** admin submits `PATCH /api/api-keys/{id}` with an unknown ID
- **THEN** the system returns 404

#### Scenario: Add token limit after current-window usage exists

- **WHEN** an API key has successful request-log token usage in the active daily window
- **AND** the API key has error or incomplete request-log token usage in the same window
- **AND** admin submits `PATCH /api/api-keys/{id}` adding a daily `total_tokens` limit without `resetUsage`
- **THEN** the new limit's `current_value` includes only the successful current-window token usage

#### Scenario: Reject a submitted monetary limit without touching history

- **GIVEN** an API key has historical monetary usage
- **WHEN** an administrator submits a new `cost_usd` or `credits` rule
- **THEN** the update returns HTTP 400 atomically
- **AND** existing keys, rules, counters and request logs remain unchanged

#### Scenario: Reset usage when adding a limit

- **WHEN** an API key has request-log usage in the active window
- **AND** admin submits `PATCH /api/api-keys/{id}` adding a limit with `resetUsage: true`
- **THEN** the new limit's `current_value` is `0`

#### Scenario: Update key transport policy override

- **WHEN** admin submits `PATCH /api/api-keys/{id}` with `{ "transportPolicyOverride": "always_http" }`
- **THEN** the system persists the override and returns `transportPolicyOverride = "always_http"`

#### Scenario: Clear key transport policy override

- **WHEN** admin submits `PATCH /api/api-keys/{id}` with `{ "transportPolicyOverride": null }`
- **THEN** the system clears the override and the key follows the global `http_downstream_transport_policy`

#### Scenario: Reject invalid transport policy override

- **WHEN** admin submits `PATCH /api/api-keys/{id}` with `{ "transportPolicyOverride": "carrier-pigeon" }`
- **THEN** the system returns 400 and does not modify the key

### Requirement: API keys can read their own `/v1/usage`

The system SHALL expose `GET /v1/usage` for self-service usage lookup by API-key clients. The route MUST require a valid API key in the `Authorization` header using the Bearer authentication scheme even when `api_key_auth_enabled` is false globally. The response MUST include only data for the authenticated key and explicitly visible aggregate upstream quota sections, and MUST return:

- `request_count`
- `total_tokens`
- `cached_input_tokens`
- `total_cost_usd` as a compatibility total of stored historical amounts, without current price calculation
- `limits[]` containing active token limits configured on the authenticated API key, with `limit_type`, `limit_window`, `max_value`, `current_value`, `remaining_value`, `model_filter`, `reset_at`, and `source`. When no API-key limits are configured and aggregate upstream quota details are visible to the caller, `limits[]` MAY mirror those aggregate upstream credit windows for legacy client compatibility.
- `upstream_limits[]` containing aggregate upstream Codex credit windows when available, with the same fields and `source: "aggregate"`, subject to the key's `usage_sections` containing `upstream_limits`
- `account_pool_usage` containing `primary` and `secondary` float remaining percentages, subject to the key's `usage_sections` containing `account_pool_usage`

Validation failures MUST use the existing OpenAI error envelope used by `/v1/*` routes.

#### Scenario: Missing API key is rejected

- **WHEN** a client calls `GET /v1/usage` without a Bearer token
- **THEN** the system returns 401 in the OpenAI error format

#### Scenario: Invalid API key is rejected

- **WHEN** a client calls `GET /v1/usage` with an unknown, expired, or inactive Bearer key
- **THEN** the system returns 401 in the OpenAI error format

#### Scenario: Key with no usage returns zero totals

- **WHEN** a valid API key with no request-log usage calls `GET /v1/usage`
- **THEN** the system returns `request_count: 0`, `total_tokens: 0`, `cached_input_tokens: 0`, `total_cost_usd: 0.0`

#### Scenario: Usage is scoped to the authenticated key

- **WHEN** multiple API keys have request-log history and one of them calls `GET /v1/usage`
- **THEN** the response includes only the usage totals and limits for that authenticated key

#### Scenario: Upstream limits are separate from API-key limits

- **WHEN** an API key with its own limit calls `GET /v1/usage`
- **AND** upstream Codex aggregate usage data exists
- **THEN** `limits[]` contains the API-key limit values
- **AND** `upstream_limits[]` contains the aggregate Codex credit windows

#### Scenario: Upstream limits are mirrored for legacy clients without API-key limits

- **WHEN** an API key without its own limits calls `GET /v1/usage`
- **AND** upstream Codex aggregate usage data is visible to the key
- **THEN** `upstream_limits[]` contains the aggregate Codex credit windows
- **AND** `limits[]` contains the same aggregate Codex credit windows for legacy client compatibility

#### Scenario: Self-usage works while global proxy auth is disabled

- **WHEN** `api_key_auth_enabled` is false and a client calls `GET /v1/usage` with a valid Bearer key
- **THEN** the system still authenticates that key and returns the self-usage payload

### Requirement: API key 7-day usage includes account cost breakdown

For historical response compatibility, `GET /api/api-keys/{key_id}/usage-7d` MAY retain `accountCosts[]` in addition to the existing 7-day totals for the selected API key. Each `accountCosts[]` item SHALL include `accountId`, `email`, `costUsd`, and `isDeleted`.

When retained, the system MUST aggregate `accountCosts[]` only from stored historical amounts in request-log rows whose `api_key_id` matches the selected key and whose `requested_at` falls inside the rolling 7-day window used by the endpoint totals.

#### Scenario: Account costs are sorted by descending cost
- **WHEN** a client loads `GET /api/api-keys/{key_id}/usage-7d`
- **AND** multiple grouped account-cost buckets exist in the 7-day window
- **THEN** `accountCosts[]` is ordered by `costUsd` descending

#### Scenario: Unknown account usage remains separate
- **WHEN** request-log rows in the 7-day window have `account_id = NULL`
- **AND** those rows are not soft-deleted
- **THEN** the response includes an `accountCosts[]` item with `accountId: null`, `email: null`, and `isDeleted: false`

#### Scenario: Deleted account usage is grouped into one bucket
- **WHEN** request-log rows in the 7-day window are marked deleted
- **THEN** the response groups their cost into a synthetic `accountCosts[]` item with `accountId: null`, `email: null`, and `isDeleted: true`

#### Scenario: Deleted and unknown account usage stay distinct
- **WHEN** the same API key has both soft-deleted request-log cost and unknown non-deleted request-log cost inside the 7-day window
- **THEN** the response returns separate `accountCosts[]` items for the deleted and non-deleted buckets

### Requirement: Request-aware API-key usage reservations

API-key usage reservation admission MUST reserve a bounded request-aware budget instead of an unconditional fixed 8192 input-token plus 8192 output-token pre-charge for every request. The reservation budget MUST be used only for admission and in-flight accounting; final token accounting MUST continue to settle to authoritative completed request usage.

For token limits, admission MUST reserve from the request input and output token budgets. The input budget MAY be estimated from self-contained request payloads, while opaque upstream context MUST fall back to a conservative input budget. The output budget MUST use a bounded system default unless codex-lb can verify that a client-provided output cap is actually enforced upstream. Retained `cost_usd` and `credits` limits MUST be excluded from reservation creation and enforcement. Reservation finalization MUST adjust every applicable reserved token value to actual completed usage exactly once, including limits whose admission reservation was zero.

#### Scenario: Concurrent priority lanes do not require 8 × 8192 output-token headroom

- **WHEN** an API key has a token limit with enough remaining tokens for the bounded request-aware reservations
- **AND** eight `gpt-5.5` requests using `service_tier = "priority"` are admitted concurrently
- **THEN** the proxy allows all eight reservations instead of rejecting a lane solely because the old 8192-output-token pre-charge would exceed the limit

#### Scenario: Opaque input uses conservative input fallback

- **WHEN** a request references input that the proxy cannot size locally, such as `previous_response_id`, `conversation`, `input_file`, or `input_image`
- **THEN** API-key admission uses the conservative default input-token reservation budget for input tokens
- **AND** final accounting still settles to actual completed usage

#### Scenario: Zero-reservation limits still settle actual usage

- **WHEN** API-key admission records a zero-delta reservation item for an applicable limit
- **AND** the request completes with non-zero actual usage for that limit
- **THEN** reservation finalization increments the limit by the actual usage instead of skipping the limit

### Requirement: Source-routed usage uses API-key reservations

The system MUST reserve API-key usage before forwarding an OpenAI-compatible
source-routed request authenticated by an API key, and MUST finalize the
reservation from the upstream OpenAI-compatible `usage` payload when the
request completes.
The finalized input, output and cached-input token values MUST update the same
API-key limit and usage-reporting paths used by subscription-backed requests.

#### Scenario: Source-routed response finalizes token usage

- **WHEN** an API key calls a source-routed model and the upstream response
  includes `usage.prompt_tokens=100` and `usage.completion_tokens=20`
- **THEN** the API-key reservation is finalized with 100 input tokens and 20
  output tokens
- **AND** `/v1/usage` for that key reflects the completed usage

#### Scenario: Missing usage fails closed for limited keys

- **GIVEN** an API key has a token limit
- **WHEN** a source-routed response succeeds but lacks usable OpenAI `usage`
  fields
- **THEN** the system does not silently finalize zero usage
- **AND** the request fails or is marked failed according to the source-routing
  error contract

## REMOVED Requirements

### Requirement: Cost accounting uses model and service-tier pricing

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: gpt-5.4 pricing is recognized

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: gpt-5.4-mini pricing is recognized

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: API key cost accounting uses the billable service tier

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: GPT-5.6 usage cost pricing matches the current published rates

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: GPT-5.6 personality pricing is recognized

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Unsupported credit limits fail closed

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Cost reservations cover cache-write and image modality rates

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Verified Astra and long-context pricing

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Published variants have independent verified rates

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Default price resolution does not guess variant prices

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Unknown pricing cannot bypass cost limits

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.
