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
