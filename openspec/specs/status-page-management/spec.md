# status-page-management Specification

## Purpose
Manage alerts, announcements, troubleshooting guides and model-assisted guidance through existing administrator settings while keeping the public status surface separate.

## Requirements

### Requirement: Status-page administration belongs to Codex LB Settings
The system SHALL provide email alert configuration and announcement management inside the existing Codex LB Settings page. These APIs SHALL require the existing dashboard administrator write permission for both reads and writes. The independent status page MUST NOT provide a second administrator login or browser administrative mutation API.

#### Scenario: Administrator manages announcements
- **WHEN** an administrator saves a draft, publishes, schedules or withdraws an announcement in Settings
- **THEN** the monitor persists the change and its public page displays only currently published announcements
- **AND** the existing dashboard session is sufficient without another login

#### Scenario: Guest cannot read private configuration
- **WHEN** a guest or unauthenticated remote caller requests status-page administration
- **THEN** private configuration, drafts and notification history are withheld

### Requirement: Service control credentials stay server-side
The Settings backend SHALL use a private configuration file under the LB data directory to connect to a literal loopback monitor address. It MUST authenticate service calls using a private credential file, reject non-loopback or redirecting control destinations, validate typed responses and redact upstream errors. SMTP passwords and control credentials MUST NOT be returned by any read endpoint.

#### Scenario: Integration has not been configured
- **WHEN** no connector configuration exists
- **THEN** Settings reports the status service as disconnected and does not send network requests

#### Scenario: SMTP authorization code is unchanged
- **WHEN** an administrator updates mail settings with no replacement password
- **THEN** the existing protected password is retained
- **AND** reads report only whether a password is configured

### Requirement: Public status uses reduced capacity and daily availability
The independent public response and display SHALL expose only the capacity-weighted remaining seven-day percentage, never account counts or per-account capacity-readiness counters. The display SHALL render daily probe availability as a calendar heatmap with Asia/Taipei dates, distinguish days without valid samples, center announcements in a full-width top row, and place incident history in a full-width bottom section.

#### Scenario: Capacity data is incomplete
- **WHEN** an eligible account's seven-day sample is missing or stale, or its plan weight is unknown
- **THEN** the aggregate percentage is unknown rather than silently excluding that account

#### Scenario: A day has no observations
- **WHEN** no valid readiness probes exist for a calendar day
- **THEN** the heatmap marks the day as unknown and does not invent a normal rate

### Requirement: Administrators manage troubleshooting content
The system SHALL allow existing dashboard administrators to list, search, create, edit, order, publish, withdraw, delete and restore structured troubleshooting guides in Settings. Reads and mutations MUST use the existing administrator-only service control channel. Structured content SHALL contain error code, title, signature, scope, cause, ordered solutions, limitations and an optional HTTP(S) address. No raw HTML SHALL be interpreted. Mutations of existing guides MUST require the current revision and return a conflict when it is stale.

#### Scenario: Administrator edits and publishes a guide
- **WHEN** an administrator saves valid content with the current revision and published status
- **THEN** the monitor persists it with an incremented revision and update timestamp
- **AND** the public troubleshooting page displays the new content in the configured order

#### Scenario: Stale editor saves
- **WHEN** a second administrator submits an outdated revision
- **THEN** the update fails with a conflict and the newer content remains unchanged

### Requirement: Guide deletion is recoverable
The monitor SHALL soft-delete guides and omit deleted, draft and withdrawn guides from public rendering and public data. Restoring a deleted guide MUST restore it as a draft requiring explicit publication. Existing static guides SHALL be imported exactly once, and restart MUST NOT overwrite edits or resurrect deleted guides.

#### Scenario: Administrator deletes and restores a published guide
- **WHEN** the guide is deleted
- **THEN** it disappears publicly but remains in the administrator's deleted list
- **WHEN** the administrator restores it using the current revision
- **THEN** it becomes a private draft

### Requirement: Public troubleshooting remains independent and safe
The existing independent troubleshooting page SHALL render published guides on the server without depending on status polling or client-side API availability. All administrator text MUST be HTML-escaped, addresses MUST reject non-HTTP(S) schemes and embedded credentials, and private content MUST NOT be embedded in public HTML or responses. Public users MUST NOT receive monitor credentials or an administrator mutation interface.

#### Scenario: Guide text contains markup
- **WHEN** a published guide contains markup-like text
- **THEN** the page displays it as text without executing HTML or scripts

#### Scenario: Status data is unavailable
- **WHEN** health/status sampling is unavailable and the content database is readable
- **THEN** the published troubleshooting page remains readable, including with JavaScript disabled

### Requirement: Administrators configure the troubleshooting model
The system SHALL let dashboard administrators configure an enabled flag, Codex LB /v1 base URL, model identifier, write-only API key and request budgets. Blank key input SHALL preserve the existing key unless clear-key is explicit. Credentials MUST remain in a private server-side file and MUST NOT appear in read responses or logs. Destination changes MUST require an explicitly supplied replacement key to avoid silently forwarding the retained credential to another origin. An explicit connection test SHALL require a completed model response, not merely health or model-list success.

#### Scenario: Administrator saves other settings
- **WHEN** the key input is blank and the destination is unchanged
- **THEN** the existing key remains usable and reads expose only a configured flag

#### Scenario: Administrator changes the model destination
- **WHEN** the base URL changes without a replacement key
- **THEN** the update is rejected and the previous configuration remains unchanged

### Requirement: Chat answers use published troubleshooting evidence
The independent troubleshooting page SHALL provide a question box above its guides. Enter SHALL submit and Shift+Enter SHALL add a newline. The service SHALL retrieve only published, non-deleted guides, provide bounded excerpts to the configured model, and return links only for validated retrieved guide identifiers. Unmatched questions SHALL receive a request for more information without calling the model. Answers MUST remain diagnostic suggestions and MUST NOT claim live verification of the user's environment.

#### Scenario: Visitor asks a covered question
- **WHEN** relevant published guides are found and the model returns a valid completed answer
- **THEN** the visitor sees the answer and source links to those guides

#### Scenario: Guide is private or removed
- **WHEN** a guide is draft, withdrawn or deleted
- **THEN** it is not included in retrieval context or citations

### Requirement: Troubleshooting assistant retains exactly one model
New assistant settings SHALL default to the exact model identifier `mercury-2.5`. Administrator saves MUST contain a single non-empty model identifier of at most 120 characters, using letters, digits, periods, underscores, colons, slashes, at signs or hyphens and starting with a letter or digit. Both the LB and monitor APIs MUST reject model arrays, list syntax and multiple names in one string. A rejected save MUST leave the previous configuration unchanged. The administrator form SHALL explain that saving another model replaces the current selection. Public chat SHALL use only the current saved selection and MUST NOT allow a visitor-supplied model.

#### Scenario: New or previously unconfigured assistant
- **WHEN** settings do not exist or an older stored model is an empty string
- **THEN** the administrator reads `mercury-2.5` as the model
- **AND** existing valid model identifiers, keys and enabled flags are preserved

#### Scenario: Administrator replaces the model
- **WHEN** an administrator saves a different valid model identifier
- **THEN** exactly that identifier replaces the previous one
- **AND** the next chat or explicit connection test uses the replacement without a model pool or fallback list

#### Scenario: Administrator submits more than one model
- **WHEN** the model is an array, a serialized list or multiple names separated by whitespace, commas or semicolons
- **THEN** the update fails validation even while the assistant is disabled
- **AND** the previous saved model and credentials remain unchanged

### Requirement: Public inference is bounded and separate from administration
Public inference MUST NOT mutate guides or access source account data, logs, credentials or system tools. Chat text SHALL be ephemeral and common credential patterns SHALL be redacted before upstream transmission. Requests SHALL have bounded input/history/output, an overall timeout, concurrency and per-peer frequency limits, and a durable daily model-call budget. Disabled or unconfigured models SHALL leave the guide page usable. Model errors SHALL be sanitized, and untrusted model text SHALL render as plain text.

#### Scenario: Daily model budget is exhausted
- **WHEN** the daily model-call budget is exhausted
- **THEN** no additional model request is sent and the visitor receives a retry-later message

#### Scenario: Model endpoint fails
- **WHEN** the configured endpoint times out, redirects, denies authentication or returns an invalid answer
- **THEN** the visitor receives a sanitized failure and can still read the guide list

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

### Requirement: Paired monitor source is distributable
The repository SHALL include the independently runnable monitor component under `deploy/status-monitor/`, with its runtime source, public static resources, dependency lock and synthetic tests. Its setup instructions MUST distinguish optional companion startup from the base LB install and MUST keep monitor state separate from source LB data. Distributed files MUST exclude runtime credentials, databases, logs, captured production requests and machine-specific diagnostic reports. Seed addresses SHALL be clearly labelled examples requiring administrator customization.

#### Scenario: Operator obtains the repository
- **WHEN** an operator checks out the version containing the troubleshooting dashboard
- **THEN** the matching monitor source and test instructions are available in the same revision
- **AND** the monitor is not automatically started or configured with production credentials

#### Scenario: Existing deployment uses customized guides
- **WHEN** the source-distribution examples are updated
- **THEN** no existing runtime guide database or running service is modified

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
