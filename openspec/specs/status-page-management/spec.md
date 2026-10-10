# status-page-management Specification

## Purpose
Manage alerts, announcements and FAQ guides through existing administrator settings while keeping the public status and FAQ surfaces separate and free of chat or model inference.

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
- **AND** the public FAQ page displays the new content in the configured order

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
The existing independent FAQ page SHALL render published guides on the server without depending on status polling or client-side API availability. All administrator text MUST be HTML-escaped, addresses MUST reject non-HTTP(S) schemes and embedded credentials, and private content MUST NOT be embedded in public HTML or responses. Public users MUST NOT receive monitor credentials or an administrator mutation interface.

#### Scenario: Guide text contains markup
- **WHEN** a published guide contains markup-like text
- **THEN** the page displays it as text without executing HTML or scripts

#### Scenario: Status data is unavailable
- **WHEN** health/status sampling is unavailable and the content database is readable
- **THEN** the published FAQ page remains readable, including with JavaScript disabled

### Requirement: Paired monitor source is distributable
The repository SHALL include the independently runnable monitor component under `deploy/status-monitor/`, with its runtime source, public static resources, dependency lock and synthetic tests. Its setup instructions MUST distinguish optional companion startup from the base LB install and MUST keep monitor state separate from source LB data. Distributed files MUST exclude runtime credentials, databases, logs, captured production requests and machine-specific diagnostic reports. Seed addresses SHALL be clearly labelled examples requiring administrator customization.

#### Scenario: Operator obtains the repository
- **WHEN** an operator checks out the version containing the FAQ dashboard
- **THEN** the matching monitor source and test instructions are available in the same revision
- **AND** the monitor is not automatically started or configured with production credentials

#### Scenario: Existing deployment uses customized guides
- **WHEN** the source-distribution examples are updated
- **THEN** no existing runtime guide database or running service is modified

### Requirement: FAQ naming and legacy navigation
The independent guide page SHALL be named Frequently Asked Questions (常见问题), and public navigation and administrator guide-management labels SHALL use that name. Its canonical address SHALL be `/static/faq.html`. The previous `/static/troubleshooting.html` address MUST redirect to the FAQ page while existing guide slugs remain unchanged. Published content and copyable addresses MUST remain readable without status polling or model configuration.

#### Scenario: Visitor opens the FAQ
- **WHEN** a visitor opens the FAQ from the overview navigation
- **THEN** the page title, heading and current navigation item display 常见问题
- **AND** published guides and their existing anchors remain available

#### Scenario: Visitor follows an old link
- **WHEN** a visitor opens `/static/troubleshooting.html`
- **THEN** the server redirects to `/static/faq.html`
- **AND** the same published guide anchor identifiers exist on the destination page

### Requirement: FAQ has no chat or model capability
The FAQ page and administrator settings MUST NOT expose chat inputs, model configuration or connection tests. The LB assistant configuration/test routes and the monitor assistant/chat routes MUST be unregistered and MUST NOT make model requests. Retired model schemas, clients, inference code and dedicated streaming assets MUST be absent from active packages. Existing assistant configuration and usage state MUST NOT be loaded or executed by the FAQ. Guide administration, status monitoring, email and announcements SHALL remain functional.

#### Scenario: A stale client calls the retired chat endpoint
- **WHEN** a client calls the previous public chat endpoint with a valid JSON body
- **THEN** it receives an unavailable route response and no model is invoked

#### Scenario: Old assistant configuration remains on disk during an upgrade
- **WHEN** the FAQ starts with a legacy assistant configuration file present
- **THEN** it does not read that file or initialize model usage state
- **AND** published guides remain available

#### Scenario: Administrator manages guide content
- **WHEN** an administrator opens the settings page
- **THEN** the FAQ guide editor remains available and there is no assistant configuration section

### Requirement: Public status exposes bounded request quality diagnostics
The public status response SHALL include a recent request-quality window separate
from the live request window. It SHALL provide sample counts, error percentage,
sample and error timestamps, and grouped error categories with counts, failure
shares, affected model names and a public FAQ slug when one exists. It MUST
exclude request IDs, account identifiers, client addresses, raw error messages,
credentials and unknown error-code strings.

#### Scenario: Current request window is idle but recent failures exist
- **WHEN** the live request window has no normal samples and the bounded recent
  window contains completed failures
- **THEN** the response SHALL retain the recent sample and failure counts and
  categories instead of returning only an empty request result
- **AND** the public page SHALL state that the live window is idle while showing
  the recent request-quality evidence

#### Scenario: Unknown error code is recorded
- **WHEN** a request log contains an error code outside the canonical category map
- **THEN** the public response SHALL classify it as an unknown/other category
- **AND** the original unknown code and raw message SHALL not appear publicly

#### Scenario: Deleted or probe request rows exist
- **WHEN** a request row is soft-deleted, marked as a non-normal internal request,
  comes from an external model source, or uses a Luna probe model
- **THEN** the row SHALL be excluded from public request-quality aggregates

### Requirement: Status page distinguishes infrastructure readiness from business quality
The status page SHALL label its calendar history as infrastructure readiness and
state that the metric excludes real model request outcomes. It SHALL present
request-quality severity and counts separately from readiness and SHALL preserve
the existing idle behavior that does not claim business success without a real
request.

#### Scenario: Infrastructure probes are healthy and recent requests are degraded
- **WHEN** readiness probes are operational and the request-quality window meets
  the configured attention threshold
- **THEN** the page SHALL show the readiness result separately and expose the
  request-quality attention state and category guidance

#### Scenario: Monitor sample is stale
- **WHEN** the latest monitor snapshot is stale or unavailable
- **THEN** the public response SHALL mark the status unknown and clear both live
  request and recent request-quality values rather than showing old green data

### Requirement: Public incident summary accounts for active incidents
The public status response SHALL include a bounded summary of recent request
incidents and SHALL count any still-open request incident even when it opened
before the recent summary window. The summary SHALL not change stored incident
rows or notification behavior.

#### Scenario: Older request incident remains open
- **WHEN** a request incident opened before the recent summary window remains
  unclosed
- **THEN** the summary SHALL report an active incident
- **AND** the page SHALL not state that there are no active request incidents

#### Scenario: Recent incidents are recovered
- **WHEN** request incidents in the recent window are all closed
- **THEN** the page SHALL show their recent count and latest recovered state while
  limiting the detailed list to a readable recent subset
