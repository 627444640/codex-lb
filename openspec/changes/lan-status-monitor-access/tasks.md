## 1. Monitor host validation

- [x] Add an `allowed_hosts` configuration field while preserving the default
  loopback behavior.
- [x] Include configured alternate hosts in `TrustedHostMiddleware` and reject
  malformed or wildcard host entries.
- [x] Add regression coverage for the canonical LAN host, an alternate LAN
  hostname, and an unlisted host.

## 2. HTTPS reverse proxy and documentation

- [x] Add the dedicated LAN HTTPS Caddy example with the LAN allowlist,
  `/internal/*` denial, and loopback upstream.
- [x] Document the port, CA requirement, root-relative host choice, and
  rollback boundary in the deployment and monitor guides.
- [x] Add the OpenSpec delta and keep the public status/FAQ and private control
  boundaries explicit.

## 3. Validation and controlled rollout

- [x] Run monitor tests, Caddy adaptation checks, and inspect the final source
  diff. The repository OpenSpec CLI was unavailable in this environment, so
  strict CLI validation remains an explicit follow-up.
- [x] Back up the runtime monitor configuration and Caddyfile, apply the LAN
  origin/listener, and restart only the monitor/Caddy jobs.
- [x] Read back loopback health, LAN HTTPS status/FAQ, control-route denial,
  the non-LAN Caddy matcher, and rollback evidence.
