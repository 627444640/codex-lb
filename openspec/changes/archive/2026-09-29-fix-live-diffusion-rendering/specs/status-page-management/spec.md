## ADDED Requirements

### Requirement: Mercury diffusion uses a bounded interactive request profile

The troubleshooting assistant SHALL request `reasoning_effort: instant` for `mercury-2`, `mercury-2.5`, and the supported legacy `mercury2.5` alias so the bounded completion budget is available for the guide-based answer. It MUST preserve `stream`, `diffusing`, structured answer validation, citations and the 2048-token completion budget. Other administrator-configured identifiers SHALL retain their existing request profile.

#### Scenario: Configured Mercury model generates an answer

- **WHEN** a retrieved-guide question is sent to `mercury-2.5`
- **THEN** the upstream request enables streaming diffusion and instant reasoning
- **AND** the final answer still requires successful termination and valid current guide citations

### Requirement: Coalesced diffusion snapshots remain visible

The visible troubleshooting chat SHALL give each received answer snapshot a bounded presentation opportunity before processing subsequent snapshots or committing completion, including when the network delivers them in one chunk. Rendering MUST use only received text and MUST NOT invent revisions. Hidden tabs SHALL skip presentation pacing. Cancellation MUST interrupt a pending presentation wait and discard provisional output.

#### Scenario: Two snapshots and completion arrive together

- **WHEN** one network chunk contains two different snapshots followed by completion
- **THEN** the browser presents the first and second received texts before committing the completed answer and sources

#### Scenario: Visitor stops while a snapshot is being presented

- **WHEN** the visitor stops generation during a pending presentation wait
- **THEN** the wait ends immediately and the provisional text is removed without entering conversation history

### Requirement: Marked diffusion drafts tolerate unstable answer field names

For a non-terminal frame with `diffusion_meta.diffusion_content: true`, the monitor MAY extract the first top-level string value as a provisional answer when its field name is still being denoised. If its key delimiter is also unstable, the monitor MAY select a longer surviving quoted text fragment using a bounded scan, because the answer is the only string value in the requested schema. The requested answer field SHALL be first. The monitor MUST omit unidentified string boundaries, numeric citation lists and known citation fields and MUST NOT render JSON scaffolding. Terminal content MUST still pass the complete answer schema and current-source checks; provisional extraction MUST NOT authorize a completed answer.

#### Scenario: The answer key is still being denoised

- **WHEN** a marked intermediate snapshot begins with a noisy answer key but retains the first string value delimiter
- **THEN** the monitor forwards that received string as a draft, without its key or citation fields
- **AND** a later valid snapshot replaces it

#### Scenario: The final JSON remains malformed

- **WHEN** the provider stops with a malformed answer object
- **THEN** the stream reports an error and does not commit the provisional answer
