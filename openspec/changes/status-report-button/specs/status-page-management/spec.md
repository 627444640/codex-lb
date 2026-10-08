## ADDED Requirements

### Requirement: Optional external problem-report navigation
The overview and FAQ pages SHALL place a `问题上报` navigation action immediately after the FAQ link when a deployment-specific HTTPS report URL is configured. The action MUST open a new tab with `noopener noreferrer` and MUST NOT replace the current-page indicator. Without a valid configuration, the action MUST remain hidden. Configuration MUST reject non-HTTPS URLs, credentials in URLs, malformed URLs, whitespace and backslashes. Portable source and tests MUST NOT contain a real deployment's report form identifier.

#### Scenario: Visitor opens the configured report form
- **WHEN** a visitor selects the configured problem-report action on either page
- **THEN** the browser opens the configured external form in a new tab
- **AND** the monitor sends no report payload and does not copy status or account data into the URL

#### Scenario: Report destination is missing or unsafe
- **WHEN** report configuration is absent, blank or invalid
- **THEN** the report action remains hidden
- **AND** overview and FAQ functionality remain available
