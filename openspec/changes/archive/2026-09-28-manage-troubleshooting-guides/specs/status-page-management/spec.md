## ADDED Requirements

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
The existing independent troubleshooting page SHALL render published guides on the server without depending on status polling or client-side API availability. All administrator text MUST be HTML-escaped, addresses MUST reject non-HTTP(S) schemes and embedded credentials, and private content MUST NOT be embedded in public HTML or responses. Public users MUST NOT receive monitor credentials or a browser mutation interface.

#### Scenario: Guide text contains markup
- **WHEN** a published guide contains markup-like text
- **THEN** the page displays it as text without executing HTML or scripts

#### Scenario: Status data is unavailable
- **WHEN** health/status sampling is unavailable and the content database is readable
- **THEN** the published troubleshooting page remains readable, including with JavaScript disabled
