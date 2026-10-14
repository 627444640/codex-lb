## ADDED Requirements

### Requirement: Response protection unavailable is retried before output

Before the proxy forwards any response event to the client, an upstream SSE `error` or `response.failed` whose code is `internal_error` and whose message is `response protection is unavailable` MUST be treated as transient. Comparison MUST ignore surrounding whitespace, collapse internal whitespace, and ignore case, and MUST NOT match a message that only contains that sentence. The proxy MUST retry on the same account and then MUST switch accounts using the existing pre-output transient retry budget. A buffered `response.created` or `response.in_progress` that has not been forwarded MUST NOT count as output and MUST NOT be forwarded for an attempt that is abandoned. The proxy MUST NOT add `internal_error` to the global admission-failure set.

After any model-output event has been observed, or any event has been forwarded to the client, the proxy MUST forward that error once and MUST NOT retry it or switch accounts.

When the retry budget is exhausted, or no other account can take the request, the client MUST receive `internal_error` and the upstream message.

Any other `internal_error` message MUST remain non-retryable.

#### Scenario: Same account succeeds before output

- **WHEN** the first upstream event is `internal_error` with message `response protection is unavailable`
- **AND** the same account's next attempt completes
- **THEN** the client receives the successful stream and does not receive the error event

#### Scenario: Another account is used after the same-account budget

- **WHEN** the same account exhausts the existing same-account transient budget on that message before any output
- **AND** another account can serve the request
- **THEN** the proxy sends the request to the other account
- **AND** the client does not receive the failed attempt's error event

#### Scenario: Output already started is not replayed

- **WHEN** a text delta has already been forwarded
- **AND** upstream then emits `internal_error` with message `response protection is unavailable`
- **THEN** the client receives that error once
- **AND** the proxy does not select another account

#### Scenario: A different internal error is terminal

- **WHEN** upstream emits `internal_error` with a message other than `response protection is unavailable` before any output
- **THEN** the proxy does not retry the account or select another account
- **AND** the client receives that error
