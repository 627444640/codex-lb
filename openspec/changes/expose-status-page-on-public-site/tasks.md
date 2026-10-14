## 1. Public mount support

- [x] Add relative URL bases and links to the status and FAQ documents.
- [x] Add regression coverage for root and `/status/` document URL resolution.
- [x] Add the public Caddy path handler and update the macOS example/docs.
- [x] Point the dashboard desktop and mobile Service status links at the
  current HTTPS origin's `/status/` path.

## 2. Validation and rollout

- [x] Run the status monitor test suite and Caddy configuration validation.
- [x] Deploy the static assets and Caddy route to the managed runtime with a
  backup and readback.
- [x] Verify public status, FAQ, API polling and public control-path denial.
