# Status-page management context

The independent monitor continues to collect availability and deliver confirmed alert events even when the LB process is unhealthy. Operators administer it only through Codex LB Settings, using the existing dashboard administrator session. The public monitor has no administrator login or browser mutation route.

The optional connector is `<CODEX_LB_DATA_DIR>/status-monitor.json` (mode 0600):

```json
{
  "url": "http://127.0.0.1:2466",
  "token_file": "/absolute/private/monitor-state/control-token.txt"
}
```

The monitor creates the credential file inside its private state directory. Connection and credential files must not be published. The LB data directory needs no new business-schema migration. Absence of the connector means disconnected/default-off. Only literal loopback destinations are accepted; redirects are not followed. A response/authentication/transport problem becomes a sanitized dashboard error, not a session logout or leaked upstream response.

SMTP authorization codes are write-only. An omitted or blank replacement keeps the previous code, and reads expose only `passwordConfigured`. The monitor writes a new private secret file and atomically changes the configuration reference; the worker uses the new settings on subsequent cycles. SMTP remains off until explicitly enabled. Announcement times use ISO 8601 in dashboard/control APIs and epoch timestamps only inside monitor persistence. All displayed calendar days use Asia/Taipei.

Seven-day capacity is weighted by the inspected LB plan-capacity constants. Incomplete fresh weekly data or an unknown plan weight yields unknown; monthly-only accounts do not create fictional weekly quota. The public response omits account counts. Calendar availability is successful readiness probes / probes with known outcomes for each local date, with sample coverage in the tooltip. It does not claim a completed business request on an idle day or invent history before monitoring began.

Example: an administrator saves a maintenance draft in Settings. It remains private. Publishing it with a future start date makes it appear in the centered announcement strip only at that time; withdrawal hides it immediately. A guest cannot read the draft or SMTP settings.

The deployment record currently defers the LB v1.24.2 rollout. This integration is implemented in source, built into a wheel and exercised through an isolated LB/monitor pair; the separate public display can be updated without restarting production LB. Installing the wheel and connector into production requires the existing controlled deployment procedure and authorization for that rollout.

## Local v1.24.3 integration — 2026-09-29

The user authorized merging this LB integration together with the independent
`feat` HTTP/SSE optimization into `v1.24.3`. The status-page source commit is
`d9973baf`, the stream feature is `f353140e`, and both were merged without conflicts.
The code retains the existing administrator boundary, optional/default-off
connector and write-only SMTP credential behavior. No migration was added.

Combined unit, API, frontend and isolated browser evidence is recorded in
`openspec/changes/integrate-status-page-settings/verification.md`, with synthetic
Settings screenshots. Source validation and production rollout remain distinct; the deployment must verify the paired monitor independently.

## Administrator-maintained FAQ guides

Guides use the same administrator session and private monitor channel as announcements. They are stored in the monitor database, with a stable public anchor, status, order, revision and timestamps. Editing requires the current revision. Soft deletion hides an entry immediately; restoring it produces a draft, so content is not accidentally republished. The seed import has a durable once-only marker and does not overwrite subsequent edits.

The public page renders structured text on the server, independently of `/api/status`; it does not expose a management API or credentials. Text is escaped, optional addresses accept HTTP(S) without embedded credentials, and deleted/private content is not included in the HTML. The monitor control API limits guide mutations to 64 KiB. Guides use no source-LB schema or production account data.

## FAQ-only retirement — 2026-09-30

The maintainer renamed the public surface to Frequently Asked Questions / 常见问题 and retired its model assistant. The canonical page is `/static/faq.html`; the legacy page address redirects, and existing guide slugs and storage keys stay unchanged. The page is server-rendered and its only optional JavaScript behavior is copying guide addresses.

The administrator retains guide CRUD and revision protection under the existing internal API names. The assistant card, configuration/test routes, public chat routes, inference modules, schemas and stream assets are removed from active packages. Existing assistant configuration and usage tables are ignored. Deployment privately archives the old configuration outside the active runtime path; it does not revoke provider credentials or drop historical data.

Model assistance and diffusion descriptions in archived changes are deprecated history. Their earlier implementation and validation remain available in the repository history and archived OpenSpec records, not as active requirements. FAQ removal has no effect on core gateway models, API keys or model-source routing.

Regression checks cover readable published guides, old-link redirects, clipboard behavior, preserved guide administration, unavailable retired APIs and zero outbound model requests even when a legacy configuration file is present.
