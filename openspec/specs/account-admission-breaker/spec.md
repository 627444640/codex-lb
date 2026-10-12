# account-admission-breaker Specification

## Purpose

Hold an account out of new assignment after a short burst of upstream admission failures, and hide one pre-output failure from the client when another healthy account can serve the request.

## Requirements

### Requirement: Admission failures open a per-account breaker

The proxy SHALL open an account's admission breaker when that account produces N consecutive qualifying failures or N qualifying failures inside the configured window. Qualifying failures SHALL be upstream `server_error`, `server_is_overloaded`, `overloaded_error`, an HTTP status of 500 or higher that is not otherwise excluded, and `stream_incomplete` only when upstream sends close code 1000 before any output. The default threshold SHALL be 3 and the default window SHALL be 60 seconds. While the breaker is open, the proxy SHALL NOT assign new unbound or soft-sticky requests to that account for the configured open interval. The default open interval SHALL be 300 seconds. After the interval, the account SHALL be half-open and SHALL accept at most one probe. A probe failure SHALL open the breaker again. A probe success SHALL close it. A success while the breaker is open SHALL NOT close it.

#### Scenario: Three failures in the window open the breaker
- **GIVEN** an account with a closed admission breaker
- **WHEN** the account returns three qualifying failures inside 60 seconds
- **THEN** the breaker is open
- **AND** new unbound requests are not assigned to that account until the open interval elapses

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

When a qualifying failure happens before any output event is forwarded to the client, the proxy SHALL retry the request at most once, after a random delay between 50 and 250 milliseconds, on a different account that is not admission-open. An HTTP status of 500 SHALL first consume the existing same-account transient retry budget of three attempts before that cross-account retry. The proxy SHALL NOT make a second cross-account retry for that request. A second qualifying failure after the cross-account retry SHALL be returned to the client. Once any output has been forwarded, the proxy SHALL NOT retry and SHALL log the failure as output interrupted mid-stream.

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

#### Scenario: Output already forwarded is not retried
- **WHEN** a qualifying failure arrives after an output event was forwarded
- **THEN** the proxy does not send the request to another account
- **AND** the failure is logged as output interrupted mid-stream

### Requirement: Continuity is not switched

The proxy SHALL NOT move a request to another account when a file pin requires that account, or when routing strategy is `single_account`. A request that depends on a `previous_response_id` SHALL stay on the owning account unless a cached full-history replay resends that turn without the anchor. Without that replay, the request SHALL fail on the owning account.

#### Scenario: previous_response_id stays on the owner without cached history
- **GIVEN** a request carries a `previous_response_id` owned by an account whose admission breaker is open
- **AND** the proxy has no cached full history for that response
- **WHEN** the proxy selects an account
- **THEN** the request is not sent to a different account

#### Scenario: cached history may leave an open owner
- **GIVEN** a pre-output failure on a previous_response owned by an admission-open account
- **AND** the cache holds the full history and the history has no file id
- **WHEN** the proxy replays the turn
- **THEN** the resend omits `previous_response_id`
- **AND** the resend may use a different healthy account

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
