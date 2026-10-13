# Add official upstream status to the public status page

## Why

The independent status monitor currently reports local gateway readiness, quota
capacity and observed request quality. Operators also need a clearly separated
view of the upstream provider's published service state so that a local request
problem can be compared with the provider's own incident signal.

## What Changes

- Add an optional, default-off OpenAI Statuspage summary collector.
- Expose a bounded, normalized `official_status` object through the existing
  public `/api/status` response.
- Render official provider state, source and fetch timestamps, selected public
  components, and bounded active incidents in a separate status-page card.
- Keep provider state out of local aggregate status, readiness history, local
  incidents and email alert state.
- Document configuration, stale/unknown behavior and the distinction between
  provider aggregate state and local model request evidence.

## Impact

This changes the optional monitor's public JSON and UI and adds an outbound
HTTPS read when explicitly enabled. It does not change the LB gateway, source
database, dashboard authentication, Caddy mount, local request-quality
calculation or monitor control paths. No database migration is required because
the monitor stores snapshots as bounded JSON payloads.
