## ADDED Requirements

### Requirement: Unsupported credit limits fail closed

The system MUST reject API key creation or submitted limit updates containing `credits` with HTTP 400 and an explanation that credit metering is unsupported. It MUST NOT assign an invented token-to-credit or currency-to-credit conversion. An existing key with any stored `credits` rule MUST fail authentication or request admission before upstream work, even when that rule has zero usage or its reset window has expired. Administrators MUST remain able to list, delete, disable, and replace these rules with supported token or cost limits.

The dashboard MUST omit credits from new limit choices and MUST explain that an existing credits rule blocks the key until it is removed or replaced. Existing credit rules MUST remain readable for remediation. Account-level upstream quota and reset-credit capabilities MUST remain unchanged. For valid keys with supported token or cost limits, `/v1/usage` MUST retain those limits and their original units separately from upstream credit windows. `/api/codex/usage` MUST NOT convert token or cost limits into Codex credit windows or balances, and MUST return null `rate_limit` and `credits` when no supported credit representation exists.

#### Scenario: Reject an unsupported submitted rule atomically

- **WHEN** an administrator creates a key or updates its limits with a credits rule
- **THEN** the endpoint returns HTTP 400 with an unsupported-metering explanation
- **AND** no key or limit changes are committed

#### Scenario: A legacy credits key cannot proxy requests

- **WHEN** a key contains an existing credits rule, including an expired rule or one with zero current usage
- **THEN** its request is rejected before upstream execution or usage reservation
- **AND** replacing that rule with a supported rule restores normal key behavior

#### Scenario: The dashboard supports remediation

- **WHEN** an administrator edits a key with an existing credits rule
- **THEN** the dashboard explains why the key is blocked
- **AND** the rule can be removed or changed to a supported type
- **AND** new rules cannot select credits

#### Scenario: Supported personal limits remain distinct from upstream credits

- **WHEN** a valid key with token or cost limits, including monthly limits, calls the usage endpoints
- **THEN** `/v1/usage` returns those limits with their original units, windows, usage, remaining values, and `api_key_limit` source
- **AND** any visible upstream credit windows remain in `upstream_limits` with `aggregate` source
- **AND** `/api/codex/usage` returns null `rate_limit` and `credits` rather than inventing a conversion or substituting upstream aggregate limits
- **AND** ChatGPT-authenticated upstream credit and monthly-window presentation remains unchanged
