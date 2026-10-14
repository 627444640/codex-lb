# Design

## Source and configuration

The monitor accepts an optional `official_status` configuration object. The
feature is disabled when the object is absent or `enabled` is false, preserving
zero-config installations. The enabled configuration uses the fixed HTTPS
OpenAI Statuspage summary endpoint and its fixed public page URL; credentials,
redirects and arbitrary caller-supplied URLs are not accepted.

The collector fetches `summary.json` with a short timeout, no redirects and a
bounded response body. It validates the page, overall status indicator,
components and incidents before producing a public-safe normalized object. The
raw response, headers, upstream error text and incident update bodies are never
stored in the public snapshot.

## Status boundaries

The normalized provider state is stored under `snapshot["official_status"]` and
is returned by `Store.public()` as `official_status`. It is deliberately not an
entry in `snapshot["components"]`: local components feed the local overall
status, readiness heatmap, incident debounce and email events.

Overall indicators map as follows: `none` to `operational`, `minor` to
`degraded`, and `major` or `critical` to `outage`. Missing, invalid or unknown
values become `unknown`. The normalized object keeps the provider's
`page.updated_at` and the local `fetched_at` as separate timestamps. A failed
fetch or expired provider sample is rendered as unknown/stale and never as
green data.

## Public UI

The overview adds an independent “OpenAI 官方状态” card. It shows the
normalized overall state, provider description, source link, both timestamps,
bounded current incidents and provider components when present. The card
includes a note that provider availability is an aggregate signal and does not
prove a local authenticated model request. The browser continues to request
only the same-origin `/api/status` endpoint; no CORS or external browser fetch
is introduced.

## Validation

Python tests cover default-off behavior, valid status mapping, malformed or
oversized responses, timeout/HTTP failure, unknown enums, stale data and public
field filtering. DOM tests cover the card, source link, timestamps, incident
rendering and unknown state. Existing local-status, history and alert tests
prove that provider data does not change local boundaries.
