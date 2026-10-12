## MODIFIED Requirements

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
