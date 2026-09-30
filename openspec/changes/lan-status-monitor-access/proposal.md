# Expose the status monitor to the LAN through HTTPS

## Why

The independent status monitor currently listens on `127.0.0.1:2466`, so the
status page can only be opened on the server Mac. The operator needs users on
the configured private LAN to read the status page and FAQ while the monitor's
administrator control channel remains private.

## What Changes

- Keep the monitor application and its Settings connector on the loopback
  listener at `127.0.0.1:2466`.
- Allow the monitor configuration to list HTTPS reverse-proxy hostnames in
  addition to the canonical `origin`, so both the LAN IP and the existing local
  hostname can be used safely.
- Provide a dedicated Caddy HTTPS listener on port `2467` for the monitor,
  restricted to the configured LAN CIDR and loopback addresses.
- Reject `/internal/*` before proxying so the LAN-facing listener cannot expose
  the monitor's service-control and administrator mutation routes.
- Document the LAN URL, internal CA requirement, connector boundary, and
  rollback procedure without publishing runtime credentials or machine state.

## Impact

This changes the status-page deployment boundary and its host validation, but
does not change the Codex LB API gateway, the status data schema, or the
loopback-only Settings connector. The LAN surface is read-only and uses the
existing HTTPS Caddy process; direct cleartext LAN binding is not supported.
