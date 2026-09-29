## REMOVED Requirements

### Requirement: Administrators configure the troubleshooting model
**Reason**: The maintainer retired the FAQ assistant and model functionality.
**Migration**: Remove active model interfaces and ignore legacy assistant state; preserve guide content and historical archives.

### Requirement: Chat answers use published troubleshooting evidence
**Reason**: The maintainer retired the FAQ assistant and model functionality.
**Migration**: Remove active model interfaces and ignore legacy assistant state; preserve guide content and historical archives.

### Requirement: Troubleshooting assistant retains exactly one model
**Reason**: The maintainer retired the FAQ assistant and model functionality.
**Migration**: Remove active model interfaces and ignore legacy assistant state; preserve guide content and historical archives.

### Requirement: Public inference is bounded and separate from administration
**Reason**: The maintainer retired the FAQ assistant and model functionality.
**Migration**: Remove active model interfaces and ignore legacy assistant state; preserve guide content and historical archives.

### Requirement: Troubleshooting chat streams diffusion snapshots
**Reason**: The maintainer retired the FAQ assistant and model functionality.
**Migration**: Remove active model interfaces and ignore legacy assistant state; preserve guide content and historical archives.

### Requirement: Diffusion streams fail safely and release capacity
**Reason**: The maintainer retired the FAQ assistant and model functionality.
**Migration**: Remove active model interfaces and ignore legacy assistant state; preserve guide content and historical archives.

### Requirement: Mercury diffusion uses a bounded interactive request profile
**Reason**: The maintainer retired the FAQ assistant and model functionality.
**Migration**: Remove active model interfaces and ignore legacy assistant state; preserve guide content and historical archives.

### Requirement: Coalesced diffusion snapshots remain visible
**Reason**: The maintainer retired the FAQ assistant and model functionality.
**Migration**: Remove active model interfaces and ignore legacy assistant state; preserve guide content and historical archives.

### Requirement: Marked diffusion drafts tolerate unstable answer field names
**Reason**: The maintainer retired the FAQ assistant and model functionality.
**Migration**: Remove active model interfaces and ignore legacy assistant state; preserve guide content and historical archives.

## MODIFIED Requirements

### Requirement: Administrators manage troubleshooting content
The system SHALL allow existing dashboard administrators to list, search, create, edit, order, publish, withdraw, delete and restore structured troubleshooting guides in Settings. Reads and mutations MUST use the existing administrator-only service control channel. Structured content SHALL contain error code, title, signature, scope, cause, ordered solutions, limitations and an optional HTTP(S) address. No raw HTML SHALL be interpreted. Mutations of existing guides MUST require the current revision and return a conflict when it is stale.

#### Scenario: Administrator edits and publishes a guide
- **WHEN** an administrator saves valid content with the current revision and published status
- **THEN** the monitor persists it with an incremented revision and update timestamp
- **AND** the public FAQ page displays the new content in the configured order

#### Scenario: Stale editor saves
- **WHEN** a second administrator submits an outdated revision
- **THEN** the update fails with a conflict and the newer content remains unchanged

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

## ADDED Requirements

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
