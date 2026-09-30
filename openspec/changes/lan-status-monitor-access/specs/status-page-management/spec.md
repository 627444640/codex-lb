## ADDED Requirements

### Requirement: The public monitor is reachable from the configured LAN over HTTPS

The deployment SHALL keep the monitor process bound to a loopback HTTP
listener and SHALL expose the public status and FAQ pages through a dedicated
HTTPS reverse-proxy listener. The canonical monitor `origin` MUST be an
HTTPS origin for the LAN listener, and configured alternate hostnames MUST pass
trusted-host validation. Direct non-loopback cleartext monitor binding MUST
remain unsupported.

#### Scenario: LAN user opens the status page

- **WHEN** a client on the configured private LAN requests the dedicated HTTPS
  monitor origin
- **THEN** the status overview, `/api/status`, static assets, and
  `/static/faq.html` are served through the proxy
- **AND** the browser does not need access to the loopback port

#### Scenario: Monitor remains private behind the proxy

- **WHEN** the monitor process starts
- **THEN** it listens only on the loopback address used by the Settings
  connector
- **AND** the public listener is provided by HTTPS Caddy rather than by a
  direct cleartext monitor socket

### Requirement: The LAN-facing proxy does not expose monitor control routes

The dedicated LAN listener MUST reject `/internal/*` before reverse proxying.
The loopback monitor control API MUST continue to require its private bearer
credential and loopback caller boundary. Public status and FAQ routes SHALL
remain anonymous read-only surfaces.

#### Scenario: LAN caller probes the control API

- **WHEN** a LAN client requests `/internal/settings`, `/internal/guides`, or
  another `/internal/*` path through the public listener
- **THEN** the proxy returns a denial without forwarding the request to the
  monitor
- **AND** no monitor credential or private configuration is returned

### Requirement: LAN exposure is restricted to the configured network

The dedicated HTTPS listener MUST allow only the configured private LAN CIDR
and loopback addresses. Requests from outside that set MUST receive a denial
before the monitor public routes are served.

#### Scenario: External source reaches the listener

- **WHEN** a request arrives from an address outside the configured LAN and
  loopback ranges
- **THEN** Caddy returns an access denial
- **AND** the monitor does not render status or FAQ content for that request

### Requirement: LAN deployment documentation states the trust and rollback boundaries

The operator documentation SHALL identify the LAN URL shape, internal CA trust
requirement, loopback connector URL, blocked control paths, and the files that
must be backed up before changing the listener. It MUST NOT publish runtime
credentials or assume that the LAN status listener is a public Internet
endpoint.
