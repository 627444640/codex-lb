## ADDED Requirements

### Requirement: Request logs persist requested, actual, and effective service tiers separately
For Responses proxy traffic, the system MUST persist the operator-requested tier, the upstream-reported actual tier when available, and the effective compatibility tier as separate request-log fields.

The legacy `fast` alias MUST be normalized to the canonical upstream value
`priority` before forwarding and before it is stored as the requested tier.
The upstream-reported `response.service_tier`, when present, remains the
authoritative actual tier even when it differs from the requested tier.

#### Scenario: Upstream reports a downgraded actual tier
- **WHEN** a client sends a Responses request with `service_tier: "priority"`
- **AND** the upstream response later reports `service_tier: "default"`
- **THEN** the persisted request log entry records `requested_service_tier = "priority"`
- **AND** the persisted request log entry records `actual_service_tier = "default"`
- **AND** the persisted request log entry records effective `service_tier = "default"`

#### Scenario: Fast alias is logged as a priority request
- **WHEN** a client sends a Responses request with `service_tier: "fast"`
- **AND** the upstream response later reports `service_tier: "default"`
- **THEN** the persisted request log entry records `requested_service_tier = "priority"`
- **AND** the persisted request log entry records `actual_service_tier = "default"`
- **AND** the persisted request log entry records effective `service_tier = "default"`

#### Scenario: Upstream omits the actual tier
- **WHEN** a client sends a Responses request with `service_tier: "priority"`
- **AND** the upstream response omits `service_tier`
- **THEN** the persisted request log entry records `requested_service_tier = "priority"`
- **AND** the persisted request log entry records `actual_service_tier = null`
- **AND** the persisted request log entry records effective `service_tier = "priority"`

### Requirement: Audio transcription usage remains token-only

Source transcription requests MUST NOT compute charges from audio duration or retained model prices. Usable token evidence MUST govern applicable token-limit settlement. When a token-limited source response has no usable token usage, the existing `usage_unavailable` behavior MUST remain enforced; a stored audio rate MUST NOT substitute for token evidence.

#### Scenario: Stored audio rate does not enable duration billing

- **GIVEN** a source model retains an old `audio_per_minute` value
- **WHEN** a transcription response reports duration
- **THEN** no duration-based monetary amount is calculated or stored
- **AND** reported token usage is retained when available

#### Scenario: Duration alone cannot satisfy a token limit

- **GIVEN** the key has an active token limit
- **WHEN** a source transcription succeeds with duration but no token-compatible usage
- **THEN** the existing missing-usage failure contract applies
- **AND** dormant monetary limits do not alter that decision

## MODIFIED Requirements

### Requirement: Responses account selection accounts for in-flight pressure

For Responses API requests, usage-based routing MUST include immediate in-process account pressure in addition to persisted usage. Account selection MUST account for in-flight response-create work, active streams, leased token pressure estimates, recent selection pressure, account health, and configured account-local caps. Selection and lease acquisition MUST be atomic with respect to other in-process selections, and the critical section MUST NOT perform database calls, network calls, sleeps, or other blocking I/O.

#### Scenario: Concurrent burst spreads before upstream usage refreshes

- **GIVEN** multiple eligible accounts have similar persisted usage
- **WHEN** many `/v1/responses` requests arrive concurrently before upstream usage refreshes
- **THEN** selected accounts are distributed according to immediate in-flight pressure and caps
- **AND** one account does not receive all requests solely because persisted usage was stale

#### Scenario: File-pinned bridge request does not reroute under local pressure

- **GIVEN** an HTTP bridge `/v1/responses` request references an `input_file.file_id` pinned to an upstream account
- **AND** that owner account or bridge session rejects admission with local pressure before output starts
- **WHEN** the proxy handles the admission failure
- **THEN** it returns the owner account overload instead of soft-rerouting the payload to another account
- **AND** the file-scoped request is not replayed to an account that does not own the file

#### Scenario: Runtime lock excludes blocking I/O

- **WHEN** account selection holds the balancer runtime lock
- **THEN** the implementation performs only in-memory scoring and lease mutation
- **AND** database, network, sleep, or bridge queue waits happen outside that lock

### Requirement: Source-routed audio transcriptions preserve OpenAI-compatible multipart semantics

Source-routed `/v1/audio/transcriptions` requests SHALL forward the inbound
audio file and non-file multipart fields to the selected source's
`/audio/transcriptions` endpoint. The proxy MUST use the stored source API key
for upstream authorization and MUST NOT forward the downstream client's
authorization credential. JSON and non-JSON successful upstream response bodies
SHALL be returned to the client with the upstream content type when present.

#### Scenario: Text transcription response passes through

- **GIVEN** an enabled OpenAI-compatible source exposes model `whisper-large-v3`
- **AND** the client requests `response_format=text`
- **WHEN** the source returns a plain text response
- **THEN** the proxy returns that response body without requiring JSON parsing

#### Scenario: Limited key requires token usage

- **GIVEN** an API key has token limits
- **AND** a source-routed audio transcription response has no token-compatible
  usage fields
- **WHEN** the upstream source returns a successful transcription response
- **THEN** the proxy releases the reservation
- **AND** returns `usage_unavailable` instead of allowing unaccounted limited-key usage

### Requirement: Responses routes preserve the Ultrafast service tier

Responses-compatible routes MUST accept the canonical `ultrafast` service tier and MUST forward it unchanged. When upstream reports the actual response tier, request logging MUST preserve `ultrafast` using the existing requested, actual, and effective tier contract.

#### Scenario: Explicit Ultrafast request is forwarded

- **WHEN** a client sends a Responses request with `service_tier: "ultrafast"`
- **THEN** the forwarded upstream payload contains `service_tier: "ultrafast"`

#### Scenario: Upstream confirms Ultrafast processing

- **WHEN** upstream completes a request with `response.service_tier: "ultrafast"`
- **THEN** the actual and effective request-log tiers are `ultrafast`

## REMOVED Requirements

### Requirement: Request logs persist requested, actual, and billable service tiers separately

**Reason:** Service-tier fields retain their routing and diagnostic meaning without a billing interpretation.

**Migration:** Keep the existing requested, actual and effective tier values and normalization; no field removal or data rewrite is required.

### Requirement: Audio transcription sources MAY bill by duration

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.
