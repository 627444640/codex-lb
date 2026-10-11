## MODIFIED Requirements

### Requirement: One pre-output full-history replay

The proxy SHALL cache completed turns of an in-flight conversation and, before any output event is forwarded to the client, SHALL resend the current turn at most once when upstream returns `previous_response_not_found`, ends the stream as `stream_incomplete` before the first output, or returns a pre-output admission failure (`server_error`, `server_is_overloaded`, `overloaded_error`, or HTTP 500 or higher) while the request still carries `previous_response_id`. The resend SHALL include the cached history, SHALL omit `previous_response_id`, and SHALL wait for a random delay between 50 and 250 milliseconds. The resend SHALL consume the same one-retry budget as admission failover. When the owning account is not admission-blocked and the failure is not an admission failure, the resend SHALL use that same account. When the owning account is admission-open, the failure is `previous_response_owner_unavailable`, or the failure is a pre-output admission failure, the resend SHALL use a different healthy account. A history that contains a file id, or a request pinned by a file, SHALL NOT move to another account. When the owning account cannot be resolved, the proxy SHALL NOT send the original `previous_response_id` to another account. After any output has been forwarded, the proxy SHALL NOT replay. A pre-output close that qualifies for the admission breaker SHALL still be recorded against that breaker, once. A second failure on the same request SHALL be returned to the client. The HTTP responses bridge SHALL apply this replay before it would otherwise fail an anchored pre-output turn.

#### Scenario: Lost previous response is resent on the same account
- **GIVEN** the cache holds the completed turns behind a `previous_response_id`
- **WHEN** upstream returns `previous_response_not_found` before any output
- **AND** the owning account is not admission-blocked
- **THEN** the proxy resends the turn once on that account
- **AND** the resend contains the cached history and no `previous_response_id`

#### Scenario: A 500 is resent without the anchor
- **GIVEN** the cache holds the completed turns behind a `previous_response_id`
- **AND** the history has no file id
- **WHEN** upstream returns `server_error` before any output
- **THEN** the proxy resends the turn once on a different healthy account
- **AND** the resend contains the cached history and no `previous_response_id`

#### Scenario: Open owner moves to a healthy account
- **GIVEN** the cache holds a full history with no file id
- **WHEN** the owning account is admission-open or returns `previous_response_owner_unavailable` before any output
- **THEN** the proxy resends the turn once on a different healthy account
- **AND** the resend contains the cached history and no `previous_response_id`

#### Scenario: Output already forwarded is not replayed
- **WHEN** a qualifying failure arrives after an output event was forwarded
- **THEN** the proxy does not resend the turn

#### Scenario: A file id does not move
- **GIVEN** the cached history or the current turn contains a file id
- **WHEN** the owning account is unavailable before any output
- **THEN** the proxy does not send the turn to a different account

#### Scenario: The close still counts
- **WHEN** upstream closes with code 1000 before any output and a history replay is staged
- **THEN** that close still counts toward the owning account's admission breaker

## ADDED Requirements

### Requirement: Shutdown releases the cache and requeued bridge waits

On graceful shutdown the proxy SHALL close the conversation history cache so unflushed turns are persisted and its SQLite connection and maintenance thread exit. A bridge request that was placed back on the pending queue to wait for another upstream event SHALL be completed or cancelled when shutdown begins, so the in-flight drain does not wait out its timeout for that request.

#### Scenario: Shutdown persists and closes the history cache
- **GIVEN** the cache holds an unflushed completed turn and its maintenance thread is running
- **WHEN** the application lifespan shuts down
- **THEN** that turn is present in the cache file
- **AND** the cache connection is closed and the maintenance thread has exited

#### Scenario: A silent requeued bridge request ends at shutdown
- **GIVEN** a bridge request was requeued onto the pending deque and is waiting for another upstream event
- **AND** the upstream sends no further event
- **WHEN** the application lifespan shuts down
- **THEN** that request receives a terminal failure
- **AND** shutdown finishes without waiting out the in-flight drain timeout
