## MODIFIED Requirements

### Requirement: Dashboard header links to the service status page

The dashboard header SHALL render a localized service-status link immediately
after the Advanced navigation control on desktop and after the Advanced
section in the mobile navigation. The link MUST derive an HTTPS status-page
origin on the current dashboard hostname at port `2467`, clear the dashboard
path/query/hash, and open in a new tab with a safe external-link relation. The
link MUST NOT add a sixth item to `CORE_NAV_ITEMS` or expose monitor control
routes.

#### Scenario: Desktop operator opens service status

- **WHEN** the dashboard header is rendered on a dashboard HTTPS origin
- **THEN** a localized Service status link appears after Advanced
- **AND** its target uses the same hostname, HTTPS, port `2467`, and root path
- **AND** it opens in a new tab

#### Scenario: Mobile operator opens service status

- **WHEN** the mobile navigation sheet is opened
- **THEN** the Service status link appears after the Advanced navigation items
- **AND** selecting it targets the same status-page origin

#### Scenario: Core navigation budget remains unchanged

- **WHEN** the header is rendered
- **THEN** the service-status link is not added to `CORE_NAV_ITEMS`
- **AND** the existing dashboard, reports, accounts, APIs and settings links
  remain unchanged
