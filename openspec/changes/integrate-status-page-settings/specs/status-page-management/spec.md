## ADDED Requirements

### Requirement: Status-page administration belongs to Codex LB Settings
The system SHALL provide email alert configuration and announcement management inside the existing Codex LB Settings page. These APIs SHALL require the existing dashboard administrator write permission for both reads and writes. The independent status page MUST NOT provide a second administrator login or browser write API.

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
