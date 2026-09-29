## ADDED Requirements

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

### Requirement: Public inference is bounded and separate from administration
Public inference MUST NOT mutate guides or access source account data, logs, credentials or system tools. Chat text SHALL be ephemeral and common credential patterns SHALL be redacted before upstream transmission. Requests SHALL have bounded input/history/output, an overall timeout, concurrency and per-peer frequency limits, and a durable daily model-call budget. Disabled or unconfigured models SHALL leave the guide page usable. Model errors SHALL be sanitized, and untrusted model text SHALL render as plain text.

#### Scenario: Daily model budget is exhausted
- **WHEN** the daily model-call budget is exhausted
- **THEN** no additional model request is sent and the visitor receives a retry-later message

#### Scenario: Model endpoint fails
- **WHEN** the configured endpoint times out, redirects, denies authentication or returns an invalid answer
- **THEN** the visitor receives a sanitized failure and can still read the guide list

## MODIFIED Requirements

### Requirement: Status-page administration belongs to Codex LB Settings
The system SHALL provide email alert configuration and announcement management inside the existing Codex LB Settings page. These APIs SHALL require the existing dashboard administrator write permission for both reads and writes. The independent status page MUST NOT provide a second administrator login or browser administrative mutation API.

#### Scenario: Administrator manages announcements
- **WHEN** an administrator saves a draft, publishes, schedules or withdraws an announcement in Settings
- **THEN** the monitor persists the change and its public page displays only currently published announcements
- **AND** the existing dashboard session is sufficient without another login

#### Scenario: Guest cannot read private configuration
- **WHEN** a guest or unauthenticated remote caller requests status-page administration
- **THEN** private configuration, drafts and notification history are withheld

### Requirement: Public troubleshooting remains independent and safe
The existing independent troubleshooting page SHALL render published guides on the server without depending on status polling or client-side API availability. All administrator text MUST be HTML-escaped, addresses MUST reject non-HTTP(S) schemes and embedded credentials, and private content MUST NOT be embedded in public HTML or responses. Public users MUST NOT receive monitor credentials or an administrator mutation interface.

#### Scenario: Guide text contains markup
- **WHEN** a published guide contains markup-like text
- **THEN** the page displays it as text without executing HTML or scripts

#### Scenario: Status data is unavailable
- **WHEN** health/status sampling is unavailable and the content database is readable
- **THEN** the published troubleshooting page remains readable, including with JavaScript disabled
