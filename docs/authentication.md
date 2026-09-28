# Authentication

This page covers **dashboard** authentication. For protecting the proxy routes that clients call, see [API Keys](api-keys.md).

## Dashboard authentication modes

`codex-lb` supports three dashboard auth modes via environment variables:

- `CODEX_LB_DASHBOARD_AUTH_MODE=standard` — built-in dashboard password with optional TOTP from the Settings page. This is the default.
- `CODEX_LB_DASHBOARD_AUTH_MODE=trusted_header` — trust a reverse-proxy auth header such as Authelia's `Remote-User`, but only from `CODEX_LB_FIREWALL_TRUSTED_PROXY_CIDRS`. Built-in password/TOTP remain available as an optional fallback, and password/TOTP management still requires a fallback password session.
- `CODEX_LB_DASHBOARD_AUTH_MODE=disabled` — fully bypass dashboard auth. Use only behind network restrictions or external auth. Built-in password/TOTP management is disabled in this mode.

`trusted_header` mode also requires:

```bash
CODEX_LB_FIREWALL_TRUST_PROXY_HEADERS=true
CODEX_LB_FIREWALL_TRUSTED_PROXY_CIDRS=172.18.0.0/16
CODEX_LB_DASHBOARD_AUTH_PROXY_HEADER=Remote-User
```

If the trusted header is missing and no fallback password is configured, the dashboard fails closed and shows a reverse-proxy-required message instead of loading the UI.

Ready-to-run Docker commands for both non-default modes are in [Docker deployment — auth mode examples](deployment/docker.md#auth-mode-examples). For Helm, pass the same values through `extraEnv`.

## First-time remote access

Setting the initial dashboard password from a remote machine requires a one-time bootstrap token — see [Getting Started](getting-started.md#remote-setup-bootstrap-token).

## Managed deployment policy

Set `CODEX_LB_DEPLOYMENT_AUTH_POLICY=managed` for the macOS HTTPS wrapper. The default `standard` preserves the existing authentication behavior for other installations. Managed policy requires standard dashboard authentication mode, an administrator password, and proxy API-key authentication. Read-only guests remain supported, with an optional guest password.

The dashboard displays the deployment requirements. Attempts to remove the administrator password or disable API-key authentication return HTTP 409 `deployment_policy_violation` before changing settings. Password changes and all guest settings remain available. The read-only `deploymentAuthPolicy` settings field can be echoed unchanged by existing clients but cannot be overridden.

`codex-lb auth-policy check --json` reads the configured SQLite database without initializing it, running migrations or contacting upstream services. Schema version 1 reports requirements, boolean state, `allowed`, and violation codes. Exit codes are 0 (allowed), 1 (policy violation), and 2 (unknown). This local deployment probe supports file-backed SQLite; unsupported databases report unknown without connecting.

The macOS wrapper runs that command from the installed application with the backend environment. HTTPS additionally requires the existing initialization marker. Guest settings do not stop the proxy. Actual loss of required authentication or an unreadable/incompatible policy result retains the emergency shutdown protection. Repeating local initialization preserves existing guest settings.

---

*Specs: [admin-auth](https://github.com/Soju06/codex-lb/tree/main/openspec/specs/admin-auth) · [api-firewall](https://github.com/Soju06/codex-lb/tree/main/openspec/specs/api-firewall)*
