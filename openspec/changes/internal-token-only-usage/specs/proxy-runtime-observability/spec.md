## ADDED Requirements

### Requirement: Request logs persist trusted client IP for client-originated traffic

The proxy MUST persist the resolved edge client IP on `request_logs.client_ip` for client-originated request-log rows when a client IP is available, including HTTP/SSE/WebSocket Responses, compact, image and source-routed requests, transcription, file creation/finalization, thread goals, control operations and explicit client warmup. The proxy MUST resolve the value using the existing trusted-proxy policy, including configured trusted proxy CIDRs and supported forwarded-client-IP headers. When no client IP is available, the persisted value MUST be `null`.

#### Scenario: Direct Responses request stores socket client IP

- **WHEN** a Responses request reaches the proxy without trusted forwarded-client-IP headers
- **THEN** the persisted `request_logs` row stores the socket client IP in `client_ip`

#### Scenario: Trusted proxy request stores forwarded client IP

- **WHEN** a Responses request reaches the proxy from a trusted proxy source with a valid forwarded-client-IP header
- **THEN** the persisted `request_logs` row stores the resolved forwarded client IP in `client_ip`

#### Scenario: HTTP bridge owner logs original client IP

- **WHEN** an origin instance forwards a Responses request to an HTTP bridge owner instance
- **THEN** the owner-side request log stores the client IP resolved by the origin instance

#### Scenario: HTTP bridge replay archives under the retried request

- **WHEN** an HTTP bridge request is retried with a new request-log row and archive id
- **AND** the ambient request id still references the old session request
- **THEN** the upstream request payload is archived under the retried request's archive id

#### Scenario: Auxiliary client operations retain IP on success and failure

- **WHEN** a client invokes transcription, file creation/finalization, thread goals, control operations or explicit warmup
- **THEN** each resulting request-log row retains the trusted ingress IP through success and failure paths
- **AND** an untrusted socket peer cannot override its source IP using a forged forwarded header

#### Scenario: Background and historical rows have no inferred device address

- **WHEN** scheduled warmup or automation creates a request log without a client
- **THEN** its client IP is null
- **AND** historical null IP values are not guessed or backfilled

#### Scenario: Client IP retains dashboard role boundaries

- **WHEN** an administrator reads request logs
- **THEN** available IP values are exposed as `clientIp` and shown in the default request-log table
- **WHEN** a guest reads or searches request logs
- **THEN** IP fields remain redacted and IP search does not disclose hidden rows

### Requirement: Request logs retain token evidence without monetary estimates

Request logs MUST preserve upstream input, output, cache-read, reported cache-write and reasoning token evidence and both requested and actual model identities. Cached reads and writes MUST be treated as disjoint input subsets, and reasoning as included in output. New logs MUST store null `cost_usd` and `pricing_version`; neither log creation nor model/usage correction may estimate a price. Failed terminal responses carrying usage MUST retain that usage without changing success-only quota settlement.

#### Scenario: Terminal failure contains usage

- **WHEN** a failed Responses event carries valid usage
- **THEN** the request log retains the tokens and failure status
- **AND** no monetary cost is generated

#### Scenario: Upstream selects a different model

- **WHEN** the response reports a model different from the requested model
- **THEN** both identities are preserved
- **AND** reported usage is recorded without looking up either model's price

### Requirement: Historical monetary evidence is preserved without repricing

Existing stored request costs and pricing versions MUST remain unchanged. Legacy API cost fields MAY expose stored historical values and aggregates of those values. Missing historical costs MUST remain unavailable; new request costs MUST remain null and MAY expose `not_applicable` in a compatible cost-status field. Reads MUST NOT compute estimates, manufacture price metadata or rewrite history. The dashboard MUST NOT render monetary totals or breakdowns.

#### Scenario: Historical stored amount survives a read

- **GIVEN** an old row stores a positive sub-cent amount and pricing version
- **WHEN** an operator reads its request-log API representation
- **THEN** the stored amount remains unrounded and unchanged
- **AND** no price lookup or write is performed

#### Scenario: New and historical null amounts stay unpriced

- **WHEN** usage is read for a row with no stored cost
- **THEN** a known model, tier or complete token count does not cause a price estimate
- **AND** the monetary amount remains null

## MODIFIED Requirements

### Requirement: Responses concurrency pressure is observable

The service MUST expose low-cardinality logs and metrics for account-local in-flight create count, active stream count, leased token pressure, cap rejections, lease stale reclaims, soft-affinity reroutes, and local-vs-upstream 429 classification. Observability MUST avoid raw prompt text, raw affinity keys, API keys, emails, request ids, session ids, and request payload content.

The service MUST expose a Prometheus gauge named `codex_lb_account_inflight_leases` labeled by `account_id` and `kind`, where `kind` is either `stream` or `response_create`. The gauge value MUST equal the current in-process account lease count for that account and kind. The gauge MUST update when a lease is acquired, explicitly released, or reclaimed as stale. Gauge labels MUST NOT include raw prompt text, raw affinity keys, API keys, emails, request ids, session ids, or request payload content.

#### Scenario: Local and upstream 429s are separated

- **WHEN** local admission rejects a request and upstream later returns a rate limit for another request
- **THEN** logs and metrics distinguish local overload reasons from normalized upstream `upstream_rate_limit`
- **AND** preserved upstream wire payloads may retain upstream codes such as `rate_limit_exceeded`, `usage_limit_reached`, or `insufficient_quota`

#### Scenario: Active account leases update gauge

- **WHEN** the proxy acquires a `stream` lease for account `acc_1`
- **THEN** `codex_lb_account_inflight_leases{account_id="acc_1",kind="stream"}` increases to the current active stream lease count
- **AND** `codex_lb_account_inflight_leases{account_id="acc_1",kind="response_create"}` remains the current active response-create lease count

#### Scenario: Released account leases reset gauge

- **WHEN** the proxy explicitly releases or stale-reclaims the last active `stream` lease for account `acc_1`
- **THEN** `codex_lb_account_inflight_leases{account_id="acc_1",kind="stream"}` is set to `0`

### Requirement: Request-log search matches client IP

Administrator request-log search MUST match persisted `client_ip` values. Guest search MUST NOT match hidden client IP fields.

#### Scenario: Search by client IP returns matching rows

- **WHEN** a request log row has `client_ip = "203.0.113.7"`
- **AND** the operator searches request logs for `203.0.113.7`
- **THEN** the matching request log row is returned

## REMOVED Requirements

### Requirement: Request logs persist client IP for Responses traffic

**Reason:** The trusted-IP requirement now covers auxiliary client operations as well as Responses.

**Migration:** Reuse the existing nullable column, trusted-proxy resolver and bridge signature; preserve historical nulls and guest redaction without a migration.

### Requirement: Request costs retain pricing and usage evidence

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Request cost precision and provenance

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.
