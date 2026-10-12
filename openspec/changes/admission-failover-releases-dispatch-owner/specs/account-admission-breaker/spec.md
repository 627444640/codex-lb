## MODIFIED Requirements

### Requirement: Continuity is not switched

The proxy SHALL NOT move a request to another account when a file pin requires that account, or when routing strategy is `single_account`. A request that depends on a `previous_response_id` SHALL stay on the owning account unless a cached full-history replay resends that turn without the anchor. A pre-output `server_error`, `server_is_overloaded`, `overloaded_error`, or HTTP status of 500 or higher on that request SHALL use the cached full history when it is present, SHALL omit `previous_response_id`, and MAY use a different healthy account. When the owning account cannot be resolved, the proxy SHALL NOT send the original `previous_response_id` to another account. Without a cached replay, the request SHALL fail on the owning account. The HTTP responses bridge SHALL follow the same rule.

On HTTP streaming, a `server_error`, `server_is_overloaded`, or `overloaded_error` that arrives before any model output and spends the one pre-output failover SHALL release the dispatch-owner binding of the failed body before the next account selection. It SHALL also request sticky reallocation. The binding SHALL be kept when a previous-response or turn-state owner is required, when a file pin or `single_account` routing applies, or when the body names `previous_response_id`, `conversation`, `prompt`, a file, container, or vector-store id, an `item_reference`, or a non-HTTP file or image URL. A hard sticky owner SHALL still be enforced by account selection. Other failure codes SHALL NOT release the binding.

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

#### Scenario: A dispatch-bound body leaves an overloaded account
- **GIVEN** an HTTP streaming body that is not account-neutral was first sent to account A
- **AND** account A returns `server_is_overloaded` after `response.created` and before any model output
- **AND** no continuity owner applies and the body names no account-scoped object
- **WHEN** the proxy spends the one pre-output failover
- **THEN** the proxy sends the same body once to a different healthy account B

#### Scenario: A file pin keeps the dispatch owner
- **GIVEN** an HTTP streaming request is pinned to account A by an input file
- **WHEN** account A returns `server_is_overloaded` before any model output
- **THEN** the proxy does not send the request to another account

#### Scenario: A non-admission failure keeps the dispatch owner
- **GIVEN** an HTTP streaming body is bound to account A
- **WHEN** account A fails before any output with a code other than `server_error`, `server_is_overloaded`, or `overloaded_error`
- **THEN** the proxy does not send the body to another account

### Requirement: Failover is visible on the request log and the breaker API

The proxy SHALL store on each new request log whether the request was admission-failed over and the account id it failed over from. Historical rows MAY leave those columns null. The dashboard API SHALL expose `GET /api/accounts/admission-breakers` with the policy, and for each account the phase `closed`, `open`, or `half_open`, consecutive and window failure counts, `open_until`, whether a probe is in flight, and the error rate over the last 1 hour and the last 24 hours. An error rate SHALL be null when that window has no requests. Error rate SHALL treat statuses other than success and cancelled as errors. Breaker phase SHALL be the phase of the replica serving the request.

On HTTP streaming, each attempt's row SHALL record the failover and history-replay marks known when that attempt started, regardless of which task finishes the attempt. The attempt sent after a failover SHALL record `admission_failover_retried` and the account it left. The failed attempt before it SHALL NOT record the failover. When retry selection ends the request and the failed attempt already wrote its row, the proxy SHALL NOT write another row for that request. A terminal row that is still written SHALL record the account whose failure is returned and the failover marks.

#### Scenario: A failed-over request records the source account
- **WHEN** a request fails over once from account A to account B
- **THEN** the request log for that request records that it was retried
- **AND** records account A as the account it failed over from

#### Scenario: Breaker status lists phase and error rates
- **WHEN** an operator calls `GET /api/accounts/admission-breakers`
- **THEN** the response includes each account's breaker phase
- **AND** includes the 1 hour and 24 hour error rates, or null when that account has no requests in the window

#### Scenario: One flagged row per failover
- **GIVEN** an HTTP streaming request fails over from account A to account B
- **WHEN** account B completes the request
- **THEN** account A's row records the error and no failover
- **AND** account B's row records `admission_failover_retried` and account A as the source

#### Scenario: No accountless row after the failed attempt logged
- **GIVEN** account A fails before any output and has written its attempt row
- **AND** no other account can be selected
- **WHEN** the proxy returns A's failure to the client
- **THEN** the request has exactly one row, on account A
- **AND** no row with a null account is written for it
