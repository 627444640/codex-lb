# Independent status and troubleshooting monitor

This optional Python 3.13 component provides the public status page, administrator-maintained troubleshooting guides and a single-model diffusion chat assistant. Its matching dashboard lives in Codex LB Settings. Normative behavior is defined in the [status-page-management specification](../../openspec/specs/status-page-management/spec.md); see the [operator guide](../../docs/status-page-management.md).

The monitor reads selected non-sensitive LB SQLite fields in read-only mode. Its own guide, sample and daily-call data are stored separately. There is no second browser administrator login: management requests use the existing LB administrator session and a private loopback service connector.

## Isolated setup

Run from this directory on a POSIX host with Python 3.13:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m monitor init
```

Initialization creates a private `runtime/config.json` and service-control credential without overwriting existing files. Review `source_db`, the separate `state_dir`, health-check URLs and `origin` before starting. Email and the model assistant stay disabled until explicitly configured. Run the service on loopback:

```sh
.venv/bin/python -m monitor serve --host 127.0.0.1 --port 2466
```

Prepare the optional LB connector in its data directory as described in the operator guide. Keep the connector and credential files private (0600); do not put their contents in Git or the browser. Public deployment requires a separately configured HTTPS reverse proxy. The optional `scripts/service.py` manages only a macOS per-user LaunchAgent and refuses to overwrite a conflicting existing definition; it is not run automatically.

Customize seeded guide addresses through **Settings → Troubleshooting guides**. Distributed addresses are examples, not working endpoints. Seed import runs only once; subsequent starts retain administrator edits, withdrawals and soft deletions.

## Assistant configuration

Use **Settings → Troubleshooting assistant** to save exactly one authorized model, gateway `/v1` address and write-only member key. The default model ID is `mercury-2.5`; a custom alias must match the gateway. Configure an upstream model source that supports Chat Completions, streaming diffusion (`diffusing`) and structured output. Run **Test saved model** before enabling public chat.

Draft snapshots replace the previous displayed text. Only validated final answers and current guide links enter follow-up history. Stopping, a failed stream or a withdrawn source removes provisional output. The model has no system tools and chat text is not persisted. Existing gateway quota-accounting buffers can delay diffusion display for usage-limited keys; verify the actual route without disabling those protections. Synthetic tests do not establish real-model availability or answer quality.

## Tests

From the repository root, after installing the existing backend/frontend development dependencies:

```sh
make test-status-monitor
```

The target runs Python tests against temporary synthetic databases and JavaScript parser/DOM tests. It does not connect to production databases or a real model. Preserve `runtime/` separately when upgrading an existing deployment; do not copy a preview database or test credential into production.

Bundled fonts retain their upstream SIL Open Font License notices: [Geist](monitor/static/fonts/OFL-Geist.txt) and [JetBrains Mono](monitor/static/fonts/OFL-JetBrainsMono.txt).
