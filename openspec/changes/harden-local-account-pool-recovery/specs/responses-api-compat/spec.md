## ADDED Requirements

### Requirement: Verified full-context stale-anchor recovery remains operation fenced

The HTTP bridge MUST recover an explicitly rejected stale previous-response
anchor only from a verified complete replacement body. Recovery MUST retain
account ownership restrictions, the durable operation identity, owner epoch and
single-settlement fence. A claimed recovery MUST not be reused by an unrelated
request or by a stale retry-circuit admission. Incremental, resource-pinned,
output-visible and ambiguous operations without the required proof MUST remain
fail-closed. The recovery must remain inside the original request budget.

#### Scenario: A complete resend can recover after an explicit stale-anchor rejection
- **GIVEN** a verified full-context resend and the required durable operation fence
- **WHEN** the upstream explicitly rejects its previous-response anchor
- **THEN** recovery submits the proven replacement body without that stale anchor
- **AND** settlement and ownership still belong to the same logical operation

#### Scenario: Missing context or a stale admission cannot claim recovery
- **GIVEN** an incremental body or an obsolete retry-circuit admission generation
- **WHEN** the request attempts stale-anchor recovery
- **THEN** no unverified replay or duplicate operation is dispatched

### Requirement: Output-free accepted capacity recovery preserves the client lifecycle

A native bridge or direct WebSocket request with only accepted lifecycle events
MAY receive one bounded recovery after an output-free capacity terminal if all
ownership, portability, output and settlement guards pass. Text, reasoning,
tool output, billed output evidence, another response identity or ambiguous
ownership MUST block this recovery. The client MUST see one response identity,
one created event, no duplicate in-progress event and one terminal outcome.
Required hard owners MUST not be excluded solely because an accepted request
is being replayed. Direct HTTP/SSE EOF recovery is outside this extension.

#### Scenario: Accepted lifecycle-only capacity rejection is recovered once
- **GIVEN** a portable request with created/in-progress events only and no output
- **WHEN** an eligible output-free capacity failure arrives
- **THEN** at most one replacement attempt can run within the original deadline
- **AND** its events preserve the client's original response lifecycle

#### Scenario: Visible output or a required owner blocks unsafe account switching
- **GIVEN** output evidence or a hard account owner that cannot be replaced
- **WHEN** recovery is considered
- **THEN** the system does not replay output or exclude the required owner

### Requirement: Shared detached-session cleanup cannot wait indefinitely on one session lock

The per-request detached-session retire sweep MUST bound each pending-lock
acquisition to five seconds. On timeout it MUST retain the session for later
cleanup without stealing lock ownership or dropping pending settlement work.
Cancellation MUST leave no abandoned lock waiter. Lifecycle owners MAY retain
the existing unbounded lock acquisition for their own drain/close path.

#### Scenario: A detached session stays busy while another request sweeps
- **GIVEN** a tracked detached session whose pending lock is held by another task
- **WHEN** the shared sweep reaches the lock-wait deadline
- **THEN** it returns from that check and leaves the session tracked
- **AND** a later pass can retire the session after it becomes drained
