## MODIFIED Requirements

### Requirement: Dashboard header links to the public status mount

The dashboard header SHALL render its localized service-status link immediately
after Advanced on desktop and after the Advanced section in the mobile menu.
The link MUST derive an HTTPS URL from the current dashboard origin, replace
the path/query/hash with `/status/`, preserve the current host and port, and
open in a new tab with a safe external-link relation. The link MUST NOT add a
sixth item to `CORE_NAV_ITEMS` or point at the private `2467` port.

#### Scenario: Public dashboard opens the mounted status page

- **WHEN** the dashboard is rendered on `https://code-never-end.dollarjudge.net`
- **THEN** the Service status link targets
  `https://code-never-end.dollarjudge.net/status/`
- **AND** it opens in a new tab

#### Scenario: LAN dashboard opens the same mounted path

- **WHEN** the dashboard is rendered on a configured LAN HTTPS origin
- **THEN** the Service status link preserves that origin's host and port and
  targets `/status/`
