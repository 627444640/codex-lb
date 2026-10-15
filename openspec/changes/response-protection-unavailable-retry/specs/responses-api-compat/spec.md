## ADDED Requirements

### Requirement: Response protection unavailable is retried before output

Before the proxy forwards any response event to the client, an upstream SSE `error` or `response.failed` whose code is `internal_error` and whose message is `response protection is unavailable` MUST be treated as transient. Comparison MUST ignore surrounding whitespace, collapse internal whitespace, and ignore case, and MUST NOT match a message that only contains that sentence. The proxy MUST retry on the same account. After that same-account budget is exhausted, the proxy MUST switch accounts at most once, and that switch MUST consume the same one-resend budget as admission failover and cached-history replay. A later failure on the same request, including another copy of this error, MUST NOT switch accounts again. A buffered `response.created` or `response.in_progress` that has not been forwarded MUST NOT count as output and MUST NOT be forwarded for an attempt that is abandoned. The proxy MUST NOT add `internal_error` to the global admission-failure set.

When the request still carries `previous_response_id`, that one switch MUST drop `previous_response_id` and resend the cached full history. When the cache does not hold that history, the proxy MUST keep retrying only the original account and MUST NOT send the request to another account.

After any model-output event has been observed, or any event has been forwarded to the client, the proxy MUST forward that error once and MUST NOT retry it or switch accounts.

When the shared switch budget is already used, the same-account budget is exhausted, or no other account can take the request, the client MUST receive `internal_error` and the upstream message.

Any other `internal_error` message MUST remain non-retryable. Other transient codes MUST keep their existing account-attempt budget.

#### Scenario: Same account succeeds before output

- **WHEN** the first upstream event is `internal_error` with message `response protection is unavailable`
- **AND** the same account's next attempt completes
- **THEN** the client receives the successful stream and does not receive the error event

#### Scenario: Another account is used after the same-account budget

- **WHEN** the same account exhausts the existing same-account transient budget on that message before any output
- **AND** another account can serve the request
- **AND** this request has not already used its one shared account switch
- **THEN** the proxy sends the request to the other account
- **AND** the client does not receive the failed attempt's error event

#### Scenario: The second account fails

- **WHEN** account A exhausts the same-account budget on that message and the proxy switches to account B
- **AND** account B also fails with that message before any output
- **AND** a third account is available
- **THEN** the client receives `internal_error` and the upstream message
- **AND** the proxy does not send the request to the third account
- **AND** the number of upstream attempts is at most the same-account budget on A plus the same-account budget on B

#### Scenario: The shared switch was already used

- **WHEN** this request already switched accounts because of an admission failure or a cached-history replay
- **AND** the current account then emits `internal_error` with message `response protection is unavailable` before any output
- **THEN** the proxy does not select another account
- **AND** the client receives that error after any remaining same-account retries

#### Scenario: An anchored image request replays cached history

- **GIVEN** an image HTTP SSE request carries `previous_response_id`
- **AND** the cache holds the completed turns behind that id
- **WHEN** the owning account exhausts the same-account budget on that message before any output
- **THEN** the proxy sends the turn once to a different account
- **AND** that request contains the cached history and no `previous_response_id`

#### Scenario: An anchored image request without cache stays on the owner

- **GIVEN** an image HTTP SSE request carries `previous_response_id`
- **AND** the cache does not hold that conversation
- **WHEN** upstream emits `internal_error` with message `response protection is unavailable` before any output
- **THEN** the proxy retries only the original account
- **AND** the proxy does not send the original `previous_response_id` to another account

#### Scenario: Output already started is not replayed

- **WHEN** a text delta has already been forwarded
- **AND** upstream then emits `internal_error` with message `response protection is unavailable`
- **THEN** the client receives that error once
- **AND** the proxy does not select another account

#### Scenario: A different internal error is terminal

- **WHEN** upstream emits `internal_error` with a message other than `response protection is unavailable` before any output
- **THEN** the proxy does not retry the account or select another account
- **AND** the client receives that error
