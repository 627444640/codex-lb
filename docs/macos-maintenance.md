# Portable macOS maintenance tooling

Owning specification: [deployment installation](../openspec/specs/deployment-installation/spec.md).

The scripts in `deploy/macos/bin/` publish the R02, R03 and R10 repairs for
an existing single-user macOS deployment. They provide bounded service
shutdown, validated backup/restore and bounded, redacted supervisor logs.
They require Python 3.12 or later for management; the application retains its
Python 3.13 requirement. They are optional operator source, separate from the
application wheel.

## Local runtime contract

Use a dedicated local runtime directory and copy the four `bin` files into
its `bin/` directory. Keep this runtime outside a Git checkout. Create
`config/`, `state/`, `logs/`, `backups/` and `certs/` locally with owner-only
permissions. Configuration is read relative to the scripts' runtime root.

The synthetic files in [examples](../deploy/macos/examples/) describe the
configuration shape. Replace all placeholder paths with actual absolute
paths locally. Do not commit the rendered files. The runtime needs:

- `config/deployment.json`: absolute `data_dir` and `manager_python`, a
  `public_url`, and `backend`/`https` command arrays with optional environment
  mappings. Launch the backend through `codex-lb` or `python -m app.cli` so
  application shutdown drains correctly.
- `config/Caddyfile`: the local HTTPS configuration. Backend and HTTPS
  health/stop probes use ports 2455 and 8443 respectively. Public examples
  expose HTTPS only on loopback; remote access requires deliberate local
  network configuration.
- `state/versions.json`: the installed `codex_lb`, exact `python` 3.13.x and
  `caddy` versions. Fill in actual versions; example values are illustrative.
- `state/runtime/caddy`: the operator-provided Caddy executable. Caddy state
  lives under `state/caddy/`; the local root certificate is exported to
  `certs/root.crt` when HTTPS readiness is checked.
- The configured data directory: application-created `store.db` and
  `encryption.key`. Complete local CA root/intermediate certificates and
  private keys under `state/caddy/pki/authorities/local/` are also required
  before a full deployment backup can pass validation.

The LaunchAgent labels are `com.local.codex-lb` and
`com.local.codex-lb.caddy`, in the current user's GUI domain. Check that these
labels and the fixed ports belong to the intended deployment before using
the management commands. The source checkout does not install LaunchAgents.

## Initialization and commands

CLI help can be viewed directly without creating any runtime configuration:

```sh
python3 deploy/macos/bin/manage.py --help
```

After provisioning the local runtime, run its `bin/codex-lbctl` wrapper with
Python 3.12+ on `PATH`. It invokes the adjacent `manage.py`. Starting the
backend first allows dashboard initialization over loopback:

```sh
bin/codex-lbctl start backend
```

Set the dashboard password, enable API key authentication and disable guest
access through the local dashboard. After confirming these settings, create
the local `state/initialized.json` marker containing `{}` with mode 0600.
This marker records operator initialization; it cannot authorize exposure on
its own. Both the manager and the HTTPS supervisor also read the actual
database authentication state and refuse HTTPS if it is missing or unsafe.
The public bundle does not include personal account or client-switching
utilities.

Typical commands from the runtime directory:

```sh
bin/codex-lbctl status
bin/codex-lbctl start https
bin/codex-lbctl stop all
bin/codex-lbctl backup
bin/codex-lbctl verify-backup backups/SELECTED-BACKUP.tar.gz
bin/codex-lbctl restore backups/SELECTED-BACKUP.tar.gz
bin/codex-lbctl logs backend --lines 60
```

Backup and restore stop services before touching their data and attempt to
recover the prior service set afterward. Unknown shutdown state is an error,
including a pending record from an earlier incomplete stop. Inspect that
state before retrying; deleting a record is not proof that a process stopped.

Restore verifies archive checksums, members, database integrity, runtime
location and required files. It supports the same runtime/data location,
not arbitrary migration to another machine. Before replacement it saves the
current files under `backups/recovery/`, even if the database is damaged or
missing. These raw snapshots are not validated backups and cannot be passed
to the normal restore command. They are not removed by healthy-backup
retention. Keep all backup material private.

If the recorded application/Python versions differ, restore uses `uv` from
`PATH` to install the recorded package version. A version string alone does
not identify a custom repair build: preserve and reinstall the specific
maintenance artifact when recovering such a build. Same-version restore
keeps the existing installed application. Optional admin/client helper files
in older backups remain accepted and are restored with the whole `bin/`
directory; new backups do not require those helpers.

## Verification

From the repository root:

```sh
make test-deployment-macos
python3 deploy/macos/tests/integration_launchagent.py
```

The unit command uses temporary files and mocked service calls. Its process
tests use isolated child processes. The second command is macOS-only and
creates one random temporary LaunchAgent, verifies the final write and final
log survive complete shutdown, then unloads the job and removes temporary
state. It does not use the deployment's service labels or data.
