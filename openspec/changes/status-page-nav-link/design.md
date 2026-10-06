# Design

The header derives the status URL at render time from `window.location`:
HTTPS is forced, the port is set to `2467`, and the path/query/hash are reset
to the status-page root. This lets the same build work for the LAN IP and mDNS
host without embedding a machine-specific address in the repository. The
current status deployment accepts those dashboard hostnames on port 2467.

The link is an ordinary external anchor with `target="_blank"` and
`rel="noreferrer"`. It is rendered after the Advanced dropdown on desktop and
after the Advanced items in the mobile sheet. It does not enter
`CORE_NAV_ITEMS`, preserving the existing core-navigation simplicity budget.
