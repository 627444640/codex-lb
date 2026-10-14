## ADDED Requirements

### Requirement: Public site exposes the read-only status mount

The maintained public HTTPS site SHALL serve the independent status monitor at
`/status/`. The mount MUST provide the overview, FAQ and public status API by
stripping the `/status` prefix before proxying to the loopback monitor. The
standalone LAN HTTPS origin on port `2467` SHALL remain supported.

#### Scenario: Public visitor opens the status overview

- **WHEN** a visitor requests `GET /status/` through the public site
- **THEN** the status overview HTML is returned
- **AND** its assets and status polling use the `/status/` mount

#### Scenario: Public visitor opens the FAQ

- **WHEN** a visitor requests `GET /status/static/faq.html`
- **THEN** the published FAQ HTML is returned
- **AND** its assets and navigation remain under `/status/`

### Requirement: Public mount keeps monitor controls private

The public site MUST return `404` for every `/status/internal/*` request and
MUST NOT forward that path to the monitor control service. Public status routes
MUST remain read-only and MUST NOT expose monitor credentials or administrator
mutations.

#### Scenario: Public caller probes a control path

- **WHEN** a caller requests `GET /status/internal/settings` through the public
  site
- **THEN** the site returns `404`
- **AND** the loopback monitor control endpoint is not invoked
