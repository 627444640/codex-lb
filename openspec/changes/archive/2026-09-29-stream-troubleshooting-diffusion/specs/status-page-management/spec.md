## ADDED Requirements

### Requirement: Troubleshooting chat streams diffusion snapshots
The assistant SHALL request Chat Completions with `stream: true`, `diffusing: true` and a structured answer/citation schema. Its new default model SHALL be `mercury-2.5`, while valid administrator-saved aliases remain unchanged. The monitor SHALL forward provisional answer snapshots as upstream events arrive; each snapshot replaces the previous text. The browser MUST render text without interpreting HTML, identify provisional output, and add history and source links only after a validated completion.

#### Scenario: A later draft revises an earlier draft
- **WHEN** the upstream emits two full-text snapshots
- **THEN** the second replaces the first instead of concatenating both
- **AND** source links and committed chat history remain absent until final validation

### Requirement: Diffusion streams fail safely and release capacity
SSE parsing MUST handle split UTF-8 and CRLF/multiline frames with bounded buffers, a 4 MiB aggregate upstream limit, 256 KiB event limit, 64 KiB text snapshot limit and a 50-second overall model-call deadline. A successful answer MUST have a valid `stop` finish reason, a `[DONE]` terminator, a valid answer schema and current retrieved citations. Errors, truncation, cancellation or source withdrawal MUST NOT commit a provisional answer. Client disconnect and explicit cancellation MUST close the upstream stream and release concurrency capacity. Existing gateway usage accounting MUST remain enforced; the UI MUST NOT synthesize diffusion steps for a buffered upstream.

#### Scenario: Upstream stops without a valid completion
- **WHEN** the stream ends without `[DONE]`, is malformed, exceeds a bound or finishes due to length
- **THEN** the client receives a sanitized failure and removes its provisional answer
- **AND** concurrency is released and existing completed history is preserved

#### Scenario: User stops generation
- **WHEN** the browser cancels the request
- **THEN** the upstream response is closed and the draft is omitted from history
