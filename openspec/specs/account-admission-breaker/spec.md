# account-admission-breaker Specification

## Purpose

Hold an account out of new assignment after a short burst of upstream admission failures, and hide one pre-output failure from the client when another healthy account can serve the request.

## Requirements

### Requirement: Admission failures open a per-account breaker

The proxy SHALL open an account's admission breaker when that account produces N consecutive qualifying failures or N qualifying failures inside the configured window. Qualifying failures SHALL be upstream `server_error`, `server_is_overloaded`, `overloaded_error`, an HTTP status of 500 or higher that is not otherwise excluded, and `stream_incomplete` before any output. On the HTTP SSE path, `stream_incomplete` before any output SHALL count without a websocket close code. On a websocket, `stream_incomplete` SHALL count only for close code 1000. One upstream failure SHALL increment the breaker at most once. A qualifying failure that arrives while the breaker is already open SHALL NOT extend `open_until`. The default threshold SHALL be 3 and the default window SHALL be 60 seconds. While the breaker is open, the proxy SHALL NOT assign new unbound or soft-sticky requests to that account for the configured open interval. The default open interval SHALL be 300 seconds. After the interval, the account SHALL be half-open and SHALL accept at most one probe. The proxy SHALL log the half-open transition once. A probe failure SHALL open the breaker again. A probe success SHALL close it. A success while the breaker is open SHALL NOT close it. Breaker phase SHALL be local to the replica that recorded the failures.

#### Scenario: Three failures in the window open the breaker
- **GIVEN** an account with a closed admission breaker
- **WHEN** the account returns three qualifying failures inside 60 seconds
- **THEN** the breaker is open
- **AND** new unbound requests are not assigned to that account until the open interval elapses

#### Scenario: An HTTP stream cut before the first token counts
- **WHEN** an HTTP SSE stream ends with `stream_incomplete` before any output and the error text has no close code
- **THEN** the failure counts toward that account's admission breaker

#### Scenario: One close increments the breaker once
- **WHEN** a single pre-output `stream_incomplete` is recorded by both the error handler and settlement
- **THEN** the account's consecutive failure count increases by one

#### Scenario: An in-flight failure does not extend an open breaker
- **GIVEN** an account whose admission breaker is already open
- **WHEN** a request that was already in flight returns a qualifying failure
- **THEN** `open_until` stays at the time recorded when the breaker opened

#### Scenario: Client-caused errors do not open the breaker
- **WHEN** an account returns `client_disconnected`, `context_length_exceeded`, `invalid_request`, `invalid_request_error`, a rate-limit code, or a quota code
- **THEN** those failures do not increment the admission breaker

#### Scenario: A frame-less close does not open the breaker
- **WHEN** an upstream websocket ends with no close code, close code 1006, or close code 1011 before any response event
- **THEN** the admission breaker does not count that drop

#### Scenario: Half-open probe recovers or reopens
- **GIVEN** an account whose open interval has elapsed
- **WHEN** the next assigned request succeeds
- **THEN** the breaker closes
- **WHEN** that probe instead returns a qualifying failure
- **THEN** the breaker opens again

### Requirement: One pre-output failover

When a qualifying failure happens before any output event is forwarded to the client, the proxy SHALL retry the request at most once, after a random delay between 50 and 250 milliseconds, on a different account that is not admission-open. That one retry SHALL be shared with a conversation-history replay on the same request, including the HTTP responses bridge and the direct websocket. An HTTP status of 500 SHALL first consume the existing same-account transient retry budget of three attempts before that cross-account retry. The proxy SHALL NOT make a second cross-account retry for that request. A second qualifying failure after the cross-account retry SHALL be returned to the client. Once any model output has been emitted, the proxy SHALL NOT retry and SHALL log the failure as output interrupted mid-stream. Model output SHALL include text deltas, tool or function-call items and arguments, and reasoning content. `output_delta_count` alone SHALL NOT decide that output has started. An admission failure after `response.created` and before that output SHALL use the same one retry. When that accepted turn still carries `previous_response_id` and cached full history is present, the retry SHALL omit `previous_response_id`, SHALL close the original upstream, and MAY use another healthy account. A client-supplied anchor without cached history SHALL NOT switch accounts. The request log for a switched request SHALL record `admission_failover_retried` and the account id it left.

#### Scenario: Pre-output server error is retried once
- **GIVEN** account A returns `server_error` before any output
- **AND** account B is eligible and not admission-open
- **WHEN** the request is not pinned to account A
- **THEN** the proxy waits for a short jitter and sends the request once to account B
- **AND** a further qualifying failure is returned to the client

#### Scenario: HTTP 500 retries the same account before failover
- **GIVEN** account A returns HTTP 500 before any output
- **AND** account B is eligible and not admission-open
- **WHEN** the request is not pinned to account A
- **THEN** the proxy calls account A three times
- **AND** then waits for a short jitter and sends the request once to account B

#### Scenario: HTTP 500 failover does not stack a history replay
- **GIVEN** account A returns HTTP 500 three times before any output
- **AND** the request carries `previous_response_id` whose history is cached
- **AND** account B then fails before any output
- **THEN** the proxy returns that failure to the client
- **AND** the proxy does not send another replay

#### Scenario: History replay spends the same retry
- **GIVEN** a request has already been resent from cached history
- **WHEN** the resend returns a qualifying admission failure before any output
- **THEN** the proxy does not send the request to another account

#### Scenario: Output already forwarded is not retried
- **WHEN** a qualifying failure arrives after an output event was forwarded
- **THEN** the proxy does not send the request to another account
- **AND** the failure is logged as output interrupted mid-stream

#### Scenario: Accepted pre-output admission failure replays cached history once
- **GIVEN** upstream has sent `response.created` and then `response.failed` with `server_error` or `server_is_overloaded`
- **AND** no text, tool call, or reasoning output has been emitted
- **AND** the cache holds the full history for `previous_response_id`
- **WHEN** the proxy handles the failure
- **THEN** it closes the original upstream and resends once without `previous_response_id`
- **AND** the request log records the failover and the account it left
- **AND** a second qualifying failure is returned to the client

#### Scenario: Accepted anchor without cached history does not switch
- **GIVEN** the same accepted admission failure
- **AND** the cache has no full history for that `previous_response_id`
- **WHEN** the anchor was supplied by the client
- **THEN** the proxy does not send the request to another account
- **AND** the failure is returned to the client

#### Scenario: Tool or reasoning output blocks accepted admission failover
- **GIVEN** upstream accepted the turn and emitted only a tool call or only reasoning content
- **WHEN** an admission failure arrives
- **THEN** the proxy does not send the request to another account

#### Scenario: Each request on a long-lived connection has its own resend
- **GIVEN** a websocket or HTTP bridge connection has already resent one request
- **WHEN** a later response.create on that same connection fails before any output
- **THEN** that later request is resent once
- **AND** the earlier resend does not consume the later request's retry

### Requirement: Continuity is not switched

The proxy SHALL NOT move a request to another account when a file pin requires that account, or when routing strategy is `single_account`. A request that depends on a `previous_response_id` SHALL stay on the owning account unless a cached full-history replay resends that turn without the anchor. A pre-output `server_error`, `server_is_overloaded`, `overloaded_error`, or HTTP status of 500 or higher on that request SHALL use the cached full history when it is present, SHALL omit `previous_response_id`, and MAY use a different healthy account. When the owning account cannot be resolved, the proxy SHALL NOT send the original `previous_response_id` to another account. Without a cached replay, the request SHALL fail on the owning account. The HTTP responses bridge SHALL follow the same rule.

#### Scenario: previous_response_id stays on the owner without cached history
- **GIVEN** a request carries a `previous_response_id` owned by an account whose admission breaker is open
- **AND** the proxy has no cached full history for that response
- **WHEN** the proxy selects an account
- **THEN** the request is not sent to a different account

#### Scenario: A 500 with cached history leaves the owner
- **GIVEN** a pre-output `server_error` on a request that carries `previous_response_id`
- **AND** the cache holds the full history and the history has no file id
- **WHEN** the proxy handles the failure
- **THEN** the resend omits `previous_response_id`
- **AND** the resend may use a different healthy account

#### Scenario: An unknown owner is not switched with the original id
- **GIVEN** a request carries a `previous_response_id` whose owner cannot be resolved
- **AND** the cache has no full history for that response
- **WHEN** the proxy selects an account
- **THEN** the request is not sent to another account with that `previous_response_id`

#### Scenario: cached history may leave an open owner
- **GIVEN** a pre-output failure on a previous_response owned by an admission-open account
- **AND** the cache holds the full history and the history has no file id
- **WHEN** the proxy replays the turn
- **THEN** the resend omits `previous_response_id`
- **AND** the resend may use a different healthy account

### Requirement: Soft preferred accounts fail over while the breaker blocks them

When an HTTP responses bridge request names a preferred account that is only a soft preference, and that account's admission breaker is open or half-open with the probe already in flight, the proxy SHALL NOT assign that account. A soft preference SHALL mean the preferred account is not an ownership pin: the HTTP bridge session key strength is not `hard`, owner check is not applied, the request is not file-pinned, routing strategy is not `single_account`, and fallback when the preferred account is unavailable remains allowed. `previous_response_id` by itself SHALL NOT make the preference hard. The proxy SHALL select another healthy account, SHALL log `admission_failover` with reason `account_admission_breaker_open`, and SHALL record the account it left. A first turn that does not carry `previous_response_id` SHALL fall back directly. When no other healthy account can take the turn, the proxy SHALL return HTTP 503 `account_admission_breaker_open` with message "No available accounts". A disabled admission breaker SHALL leave this selection unchanged. A half-open account whose probe slot is free SHALL remain eligible for that probe. An ownership pin, including key strength `hard`, owner check applied, `require_same_account`, a file pin, and `single_account` routing, SHALL stay on the pinned account. A hard Codex session owner that is not an ownership pin SHALL still fail with HTTP 503 `account_admission_breaker_open` and SHALL NOT be served by another account.

#### Scenario: Soft preferred breaker open uses another healthy account
- **GIVEN** account A is the soft preferred account and its admission breaker is open
- **AND** account B is eligible and not admission-blocked
- **AND** the request does not carry `previous_response_id`
- **WHEN** the proxy selects an account
- **THEN** the request is served by account B
- **AND** the failover from account A is recorded with reason `account_admission_breaker_open`

#### Scenario: Soft preferred breaker open with no other healthy account returns 503
- **GIVEN** account A is the soft preferred account and its admission breaker is open
- **AND** no other healthy account is eligible
- **WHEN** the proxy selects an account
- **THEN** the response is HTTP 503 `account_admission_breaker_open`

#### Scenario: Half-open probe already taken falls back
- **GIVEN** account A is the soft preferred account
- **AND** its admission breaker is half-open and the probe is already in flight
- **AND** account B is eligible and not admission-blocked
- **WHEN** the proxy selects an account
- **THEN** the request is served by account B

#### Scenario: Hard Codex owner stays unavailable
- **GIVEN** a hard Codex session owner mapping names account A
- **AND** that mapping is not an ownership pin
- **AND** account A's admission breaker is open
- **AND** account B is eligible
- **WHEN** the proxy selects an account
- **THEN** the response is HTTP 503 `account_admission_breaker_open`
- **AND** the request is not served by account B

#### Scenario: Ownership pin stays on the open account
- **GIVEN** the preferred account is an ownership pin whose admission breaker is open
- **AND** another healthy account is eligible
- **WHEN** the proxy selects an account
- **THEN** the pinned account is still selected

#### Scenario: Disabled breaker keeps the preferred account
- **GIVEN** the admission breaker is disabled
- **AND** the soft preferred account would otherwise be admission-open
- **WHEN** the proxy selects an account
- **THEN** the preferred account is selected

### Requirement: Failover is visible on the request log and the breaker API

The proxy SHALL store on each new request log whether the request was admission-failed over and the account id it failed over from. Historical rows MAY leave those columns null. The dashboard API SHALL expose `GET /api/accounts/admission-breakers` with the policy, and for each account the phase `closed`, `open`, or `half_open`, consecutive and window failure counts, `open_until`, whether a probe is in flight, and the error rate over the last 1 hour and the last 24 hours. An error rate SHALL be null when that window has no requests. Error rate SHALL treat statuses other than success and cancelled as errors. Breaker phase SHALL be the phase of the replica serving the request.

#### Scenario: A failed-over request records the source account
- **WHEN** a request fails over once from account A to account B
- **THEN** the request log for that request records that it was retried
- **AND** records account A as the account it failed over from

#### Scenario: Breaker status lists phase and error rates
- **WHEN** an operator calls `GET /api/accounts/admission-breakers`
- **THEN** the response includes each account's breaker phase
- **AND** includes the 1 hour and 24 hour error rates, or null when that account has no requests in the window
