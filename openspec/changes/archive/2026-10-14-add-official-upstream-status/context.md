# Context

The monitor's existing status is intentionally local: gateway probes, read-only
source collection, quota capacity and real request outcomes. OpenAI's public
Statuspage is an external aggregate signal and can disagree with a particular
account, model or local proxy. Keeping it under `official_status` prevents an
upstream incident from changing local readiness history, incident debounce or
email alerts.

The provider endpoint is read only and public, but its payload is still an
untrusted external document. The adapter therefore fixes the HTTPS host and
path, bounds the streamed body, applies a total read deadline, accepts only
known status values, omits raw incident updates and exposes only text-safe,
bounded fields. A provider failure is observable as unknown/stale and is not a
monitor-cycle failure.

The feature is default-off because it adds an outbound dependency to an
otherwise local monitor. Operators opt in through the private runtime config
and restart the monitor to load the setting. The public page continues to call
only its same-origin status endpoint, preserving the current CSP and public
mount boundary.
