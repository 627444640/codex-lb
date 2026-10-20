## ADDED Requirements

### Requirement: Upstream stream errors are stored and logged once

When an upstream SSE `error` or `response.failed` ends a stream attempt, the request log MUST set `failure_phase` to `upstream`, `upstream_error_code` to the upstream error code, and `failure_detail` to one line containing the upstream message and, when present, `type=` and `param=`. Whitespace in those values MUST be collapsed and each value MUST be length-capped. The proxy MUST emit one console line for that attempt containing the request id, account id, code, type, param, message, and whether the pre-output response-protection retry was used. That line MUST NOT include credentials, authorization headers, or the request body. An existing `stream_incomplete` failure detail of `upstream_eof_before_terminal_event` MUST be preserved, and its `upstream_error_code` MUST be `stream_incomplete`.

#### Scenario: Response-protection failure fills the request log

- **WHEN** upstream emits `internal_error` with message `response protection is unavailable`, type `server_error`, and param `input_image`
- **THEN** the failed attempt's request log stores `upstream_error_code` `internal_error`
- **AND** `failure_phase` is `upstream`
- **AND** `failure_detail` contains the message, `type=server_error`, and `param=input_image`
- **AND** one console line contains those fields and does not contain the request body or credentials

### Requirement: Request-log search matches the archive request id

Request-log search MUST match `archive_request_id` as well as `request_id`. A successful image request that bypasses the HTTP bridge MUST still write a request log whose `archive_request_id` is the inbound request id printed on the bypass log and whose `request_id` is the upstream response id.

#### Scenario: Bypass log id finds the success row

- **WHEN** an `input_image` request bypasses the HTTP bridge and upstream completes with a response id
- **THEN** a success request log exists
- **AND** its `archive_request_id` equals the request id in the bypass log
- **AND** searching request logs for that inbound id returns the row

### Requirement: Body-parse 400s are request logs

When an OpenAI-format route fails with HTTP 400 and detail `There was an error parsing the body`, the proxy MUST write a request log with status `error`, error code `invalid_request_error`, that detail as the error message, `failure_phase` `validation`, and `failure_detail` set to the causing exception type. `upstream_status_code` MUST be null. `api_key_id` MUST be null. The request body MUST NOT be stored. A failure to write the row MUST still return the HTTP 400. Other HTTP 400 details, JSON validation errors, and dashboard-format routes MUST NOT be recorded by this path.

#### Scenario: Client disconnect during body read is recorded

- **WHEN** reading a `/v1/` JSON body raises an exception other than a JSON decode error
- **THEN** the client receives HTTP 400 with detail `There was an error parsing the body`
- **AND** a request log stores `failure_phase` `validation` and the cause type
- **AND** the stored row does not contain the request body
