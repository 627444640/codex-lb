# Independent status and FAQ monitor

This optional Python 3.13 component provides the public status page, administrator-maintained FAQ guides. Its matching dashboard lives in Codex LB Settings. Normative behavior is defined in the [status-page-management specification](../../openspec/specs/status-page-management/spec.md); see the [operator guide](../../docs/status-page-management.md).

The monitor reads selected non-sensitive LB SQLite fields in read-only mode. Its own guide and sample data are stored separately. There is no second browser administrator login: management requests use the existing LB administrator session and a private loopback service connector.

The optional `official_status` setting in the private `runtime/config.json`
adds a separate OpenAI provider-status card to the public page. It is disabled by default and does not affect local
gateway health, readiness history, request quality, incidents or email alerts.
Enable it in the private runtime configuration, then restart the monitor so the
new settings are loaded, only when the host is allowed to make the outbound
HTTPS request:

```json
{
  "official_status": {
    "enabled": true,
    "url": "https://status.openai.com/api/v2/summary.json",
    "page_url": "https://status.openai.com/",
    "stale_seconds": 300
  }
}
```

The monitor validates the fixed OpenAI Statuspage source, bounds the response,
and exposes only normalized status, timestamps, public component names and a
small incident summary through `/api/status`. A timeout, invalid response or
expired sample is shown as unknown/stale. `page_updated_at` is the provider's
timestamp; `fetched_at` is the local monitor read time. The provider status is
an aggregate signal and does not prove a successful authenticated model
request on this LB.

## Isolated setup

Run from this directory on a POSIX host with Python 3.13:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m monitor init
```

Initialization creates a private `runtime/config.json` and service-control credential without overwriting existing files. Review `source_db`, the separate `state_dir`, health-check URLs and `origin` before starting. Email stays disabled until explicitly configured. Run the service on loopback:

```sh
.venv/bin/python -m monitor serve --host 127.0.0.1 --port 2466
```

Prepare the optional LB connector in its data directory as described in the operator guide. Keep the connector and credential files private (0600); do not put their contents in Git or the browser. The monitor process remains on loopback even when the public page is opened by other LAN clients. Use a separate HTTPS reverse-proxy listener (the maintained macOS example uses port `2467`) and keep the `/internal/*` control paths denied at that proxy. Set `origin` to the canonical HTTPS LAN origin and list any additional LAN host aliases in `allowed_hosts`; do not use a cleartext non-loopback listener. The optional `scripts/service.py` manages only a macOS per-user LaunchAgent and refuses to overwrite a conflicting existing definition; it is not run automatically.

For a LAN deployment using the maintained example, the public status page is served at a configured HTTPS origin such as `https://status.example.lan:2467/`; an additional mDNS or IP alias may be listed in `allowed_hosts`. LAN clients must trust the Caddy internal CA certificate. The Settings connector remains `http://127.0.0.1:2466` and is never replaced with the LAN URL. Hostnames, IP addresses and certificates are deployment values, not portable source defaults; update the private runtime copy when the LAN address changes.

Customize seeded guide addresses through **Settings → Frequently asked questions**. Distributed addresses are examples, not working endpoints. Seed import runs only once; subsequent starts retain administrator edits, withdrawals and soft deletions.

## FAQ and upgrades

The guide-only FAQ lives at `/static/faq.html`. Old `/static/troubleshooting.html` links redirect to the new page; existing guide anchors and administrator edits remain valid. There is no chat UI, model configuration or inference endpoint.

Before upgrading, preserve `runtime/` and privately archive any retired `troubleshooting-assistant.json` outside the active runtime directory. The new component does not read it. Do not copy preview data or credentials into an existing deployment, and do not drop old tables as part of this feature removal.

## Tests

From the repository root, after installing the existing backend/frontend development dependencies:

```sh
make test-status-monitor
```

The target runs Python tests against temporary synthetic databases and FAQ clipboard/DOM tests. The tests do not connect to production databases or model providers. Preserve `runtime/` separately when upgrading an existing deployment; do not copy a preview database or test credential into production.

Bundled fonts retain their upstream SIL Open Font License notices: [Geist](monitor/static/fonts/OFL-Geist.txt) and [JetBrains Mono](monitor/static/fonts/OFL-JetBrainsMono.txt).
