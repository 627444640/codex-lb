## ADDED Requirements

### Requirement: Invalid upstream usage cannot reduce prior token consumption

Token counters used for accounting MUST be non-negative integers. Invalid upstream usage MUST NOT be settled as valid consumption or reduce consumption from previous requests. Reservation release and refunds for valid usage below the reservation MUST remain supported and idempotent. Invalid usage MUST remain distinguishable from valid zero usage.

#### Scenario: Negative upstream token count
- **GIVEN** a key has 100 tokens of previous settled usage and an active 30-token reservation
- **WHEN** upstream usage reports input -10 and output 5
- **THEN** that usage is rejected as accounting evidence and no finalization decreases previously settled usage below 100

#### Scenario: Valid reservation refund
- **GIVEN** a key has 100 tokens of previous settled usage and an active 30-token reservation
- **WHEN** a successful request reports input 10 and output 5
- **THEN** the final settled counter is 115 and repeated finalization or release does not change it

### Requirement: Model-source Responses terminal outcomes govern settlement

Model-source Responses streams MUST preserve explicit completed, failed and incomplete terminal outcomes independently of HTTP status or normal connection EOF. Failed and incomplete terminal responses MUST NOT be logged as successful or finalize success-only token limits; any reservation MUST be released exactly once. Valid usage reported on an unsuccessful terminal MUST remain available in the request log. Completed valid streams MUST retain normal settlement. A Responses stream that ends without a terminal outcome MUST NOT be assumed successful merely because usage was observed. Chat-completion stream behavior MUST remain compatible.

#### Scenario: Failed Responses stream with usage
- **WHEN** a model source sends HTTP 200 followed by response.failed with input 100 and output 20
- **THEN** the downstream receives the failure event, the log records failure and known usage 120, and the key reservation is released without counting a successful request

#### Scenario: Failed non-streaming Responses result
- **WHEN** a model source returns HTTP 200 with an explicit failed or incomplete JSON response status
- **THEN** the response body and valid reported usage are preserved, the log records failure, and the key reservation is released

#### Scenario: Incomplete or unterminated Responses stream
- **WHEN** a model source emits response.incomplete or ends before a terminal event
- **THEN** the log does not report success and the reservation does not finalize as successful consumption

#### Scenario: Completed Responses stream
- **WHEN** a model source emits response.completed with valid complete usage
- **THEN** the request is logged as successful and its reservation is finalized once using the reported input and output

#### Scenario: Downstream cancellation after a known terminal
- **WHEN** a downstream cancellation occurs after a model-source Responses terminal outcome is known
- **THEN** a known failed or incomplete outcome remains failed and releases its reservation
- **AND** a known completed outcome with valid usage settles exactly once before cancellation propagates
- **AND** cancellation before any terminal remains cancelled and releases the reservation

#### Scenario: Upstream terminal error contains sensitive text
- **WHEN** a failed or incomplete SSE or JSON result contains arbitrary upstream error text
- **THEN** the downstream response remains compatible and persisted error fields use safe classifications and summaries rather than arbitrary upstream text

### Requirement: Known-token totals are consistent and partial usage remains explicit

For the same request set and time window, request logs, reports, dashboard cards and trends MUST use the same known-token total: known input plus reported output, or known reasoning when output is absent. Reasoning MUST NOT be added again when output exists; cache-read and cache-write MUST NOT be added to total input. Aggregation MUST use this rule before and after hourly folding without rewriting historical rows or changing the schema. Request-log responses and UI MUST distinguish complete, partial and missing usage. Aggregate totals MUST be described as known reported usage rather than a guarantee of complete actual upstream consumption.

#### Scenario: Partial usage before and after folding
- **GIVEN** one request has input 100, output absent and reasoning 20
- **WHEN** matching log, report and dashboard totals are read before or after hourly aggregation
- **THEN** all return known total 120 and the request is identified as partial usage
- **AND** neither response nor UI claims that 20 is complete measured output

#### Scenario: Complete usage with subsets
- **GIVEN** one request has input 100, output 40, reasoning 20 and cached input 30
- **WHEN** its usage is displayed or aggregated
- **THEN** total usage is 140 and identified as complete, without counting reasoning or cached input twice

#### Scenario: Missing usage
- **WHEN** a request has no input, output or reasoning usage
- **THEN** its request-log usage is marked missing and an absent total is not presented as measured zero
