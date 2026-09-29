# Independent status and FAQ monitor

This optional Python 3.13 component provides the public status page, administrator-maintained FAQ guides. Its matching dashboard lives in Codex LB Settings. Normative behavior is defined in the [status-page-management specification](../../openspec/specs/status-page-management/spec.md); see the [operator guide](../../docs/status-page-management.md).

The monitor reads selected non-sensitive LB SQLite fields in read-only mode. Its own guide and sample data are stored separately. There is no second browser administrator login: management requests use the existing LB administrator session and a private loopback service connector.

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

Prepare the optional LB connector in its data directory as described in the operator guide. Keep the connector and credential files private (0600); do not put their contents in Git or the browser. Public deployment requires a separately configured HTTPS reverse proxy. The optional `scripts/service.py` manages only a macOS per-user LaunchAgent and refuses to overwrite a conflicting existing definition; it is not run automatically.

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
