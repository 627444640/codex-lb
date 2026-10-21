## ADDED Requirements

### Requirement: Bridge admission failures identify their actual gate

A proxy-generated bridge refusal MUST distinguish an active circuit cooldown from an occupied half-open probe, a changed recovery generation, and unavailable recovery persistence. The distinction MUST NOT grant a new replay, reset a request deadline, clear a durable circuit, or weaken operation ownership checks. A cooldown loaded from durable state MUST have the same external meaning as a locally observed cooldown.

#### Scenario: Future circuit deadline is reported as a local cooldown
- **GIVEN** a hard-affinity bridge request is refused by a circuit with a future cooldown deadline
- **WHEN** its HTTP response has not started
- **THEN** the proxy returns HTTP 503 with OpenAI error code `bridge_session_cooldown`
- **AND** `Retry-After` is the positive remaining duration rounded up to integer seconds
- **AND** no replacement upstream request is dispatched solely because the error code changed

#### Scenario: Half-open occupancy is not a fictitious timeout
- **GIVEN** a bridge circuit cooldown has expired but its half-open probe remains occupied
- **WHEN** an ordinary request is refused before dispatch
- **THEN** the proxy reports temporary unavailability rather than an upstream timeout or active session cooldown
- **AND** it does not invent a cooldown deadline or a one-second Retry-After value

#### Scenario: Recovery generation conflict does not mint another replay
- **GIVEN** a verified recovery attempt captured an earlier circuit generation
- **AND** the durable generation claim fails because another attempt has advanced it
- **WHEN** the proxy handles that refusal
- **THEN** it sends no replacement request for that failed claim
- **AND** it distinguishes the generation conflict from a proven active cooldown

#### Scenario: Recovery persistence is unavailable
- **WHEN** a required recovery-generation read or claim cannot complete
- **THEN** the proxy preserves the existing fail-closed recovery-persistence behavior
- **AND** the failure is not converted into proof that the upstream request timed out
- **AND** no fresh recovery budget is allocated

#### Scenario: An already-started stream retains one terminal failure
- **GIVEN** an HTTP SSE response has already started
- **WHEN** a bridge admission refusal must be surfaced
- **THEN** the proxy emits exactly one protocol-compatible terminal failure event
- **AND** it does not attempt to replace the committed HTTP status or headers
- **AND** any genuine retry hint uses the existing SSE millisecond retry format

#### Scenario: Actual upstream timeouts keep their existing classification
- **WHEN** upstream execution times out or the original request budget is exhausted
- **THEN** the proxy retains the existing upstream timeout or budget-exhaustion error contract
- **AND** it does not relabel the event as a bridge session cooldown

### Requirement: Recovery cleanup preserves per-attempt evidence

Bridge recovery cleanup MUST preserve the existing classification and replay authorization of each physical response-create attempt. A matched explicit previous-response rejection MUST NOT make sibling requests account-neutral, circuit-neutral, or replay-safe. Repeated observations of the same physical attempt MUST remain deduplicated, while a distinct new send MUST remain independently observable.

#### Scenario: A rejected request does not rewrite its siblings
- **GIVEN** one pending request has an explicit previous-response rejection
- **AND** a sibling was sent but has no response event
- **AND** another sibling has an observed response event
- **WHEN** recovery cleanup retires their shared transport
- **THEN** the eventless sent sibling retains its UNKNOWN evidence
- **AND** the eventful sibling retains its ACKNOWLEDGED evidence
- **AND** each sibling retains its existing circuit eligibility and replay guards

#### Scenario: Local cleanup is not a second upstream failure
- **GIVEN** a physical response-create attempt has already had its failure observed
- **WHEN** a delayed reader, cleanup or settlement observes that same attempt again
- **THEN** no second circuit strike is recorded for that attempt
- **AND** the observation does not create a new transparent-replay opportunity

#### Scenario: A new send is not suppressed by an older observer
- **GIVEN** a request has a distinct authorized replacement send
- **WHEN** that new physical attempt fails and an old observer also completes
- **THEN** the new attempt remains independently countable under the existing rules
- **AND** the old observer cannot duplicate its own strike or erase the new evidence
