## ADDED Requirements

### Requirement: Replayed request history preserves independent tool calls

For Responses request history, the service MUST retain different nonblank tool call IDs as independent calls even when their names, arguments, and optional namespaces match. This requirement includes flat legacy calls and parallel wrappers. The corresponding tool outputs MUST remain tool outputs paired to their original call IDs. The service MAY suppress exact historical replays with the same call ID and canonical arguments, and MUST preserve existing namespace isolation.

#### Scenario: Consecutive terminal polls have identical arguments

- **WHEN** an HTTP bridge follow-up with `previous_response_id` contains two `write_stdin` calls with the same parameters, different call IDs, and their respective outputs
- **THEN** both calls and outputs remain in the forwarded request
- **AND** the later terminal output is not converted into an assistant message

#### Scenario: Independent parallel wrappers share arguments

- **WHEN** request history contains two parallel wrappers with different call IDs and equal ordinary, code-mode, or mixed tool arguments
- **THEN** both wrappers and their paired outputs remain in the forwarded request

#### Scenario: A historical call is replayed exactly

- **WHEN** the same historical side-effect call ID and canonical arguments recur within a user turn
- **THEN** the existing replay suppression can remove the duplicate call while retaining its output content

### Requirement: HTTP bridge downstream buffering is bounded

HTTP bridge response queues MUST enforce both a per-request retained-event byte limit and a shared process byte limit, including prewarm and durable replay queues. Enqueuing events MUST NOT wait for a downstream client to consume them. The default limits SHALL be 32 MiB per request and 256 MiB per process, counting retained string storage and queue references.

When either limit would be exceeded, the service MUST release that request's buffered events and signal a `downstream_buffer_overflow` failure to its consumer. It MUST NOT silently report successful delivery or penalize an upstream account for this local failure. Other request queues MUST remain usable. Further events for the failed queue MUST NOT accumulate in memory.

Existing upstream work MUST retain its terminal persistence and usage-settlement owner after the downstream consumer detaches. A detached overflowed request's API-key reservation MUST remain available to terminal settlement or the existing bounded upstream failure cleanup. Consuming, detaching, or discarding a queue MUST return its retained-event budget.

#### Scenario: A slow consumer exhausts its request budget

- **WHEN** an upstream reader produces more events than its paused downstream queue can retain
- **THEN** the reader continues without waiting for that consumer
- **AND** the consumer receives an explicit buffer overflow failure when it resumes
- **AND** the accumulated events release their memory budget immediately

#### Scenario: Several requests exhaust the shared budget

- **WHEN** a new event exceeds the process budget while another request has buffered events
- **THEN** only the queue receiving the excess event fails
- **AND** another request can continue consuming and release capacity

#### Scenario: Upstream completes after overflow and downstream detach

- **WHEN** an overflowed request's client stops consuming before upstream completion
- **THEN** the upstream terminal handler retains responsibility for durable outcome and API-key usage settlement
- **AND** downstream overflow alone does not change account health

## MODIFIED Requirements

### Requirement: Namespaced side-effect replay dedupe preserves call identity

For a namespaced side-effect function or custom-tool call, the service MUST use the call's namespace and call ID as part of downstream and replayed-history deduplication identity. An exact replay with the same namespace, name, call ID, and canonical arguments MUST remain suppressed. Calls with different namespaces or different nonblank call IDs MUST remain distinct, even when their names and canonical arguments match, and their matching outputs MUST remain in forwarded history.

Flat legacy downstream side-effect events MAY continue to use argument-based replay identity for reconnect recovery. This exception MUST NOT apply to request history containing different nonblank call IDs.

#### Scenario: Distinct namespaced spawns use identical arguments

- **WHEN** two `collaboration.spawn_agent` calls have identical arguments and different call IDs
- **THEN** both calls are forwarded
- **AND** both matching outputs remain in replayed request history

#### Scenario: Exact namespaced call is replayed after reconnect

- **WHEN** reconnect replay emits the same namespaced call ID and canonical arguments under a new response ID
- **THEN** the service suppresses the replayed downstream call

#### Scenario: Equal call identity appears in different namespaces

- **WHEN** two side-effect calls share a name, call ID, and arguments but have different namespaces
- **THEN** the service treats them as distinct calls
