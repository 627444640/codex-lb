# Align managed deployment authentication policy

## Why

The dashboard supports read-only guests, but the macOS HTTPS supervisor stops the entire proxy when guest access is enabled. Settings writes succeed before the independent deployment rule rejects them. Initialization also silently disables guests.

## What Changes

- Add an opt-in managed authentication policy, shared by mutation validation, dashboard capabilities, and a read-only CLI probe. Standard installations retain existing behavior.
- Managed deployments require an administrator password and proxy API-key authentication. Guest access remains read-only with an optional password.
- Reject attempts to disable required authentication before changing state, with HTTP 409 `deployment_policy_violation`.
- Use the installed policy probe for HTTPS supervision and status; preserve emergency fail-closed behavior and provisioning markers.
- Preserve guest choices when initialization is repeated. No database migrations or credential changes.

## Impact

Admin authentication, settings responses and UI, CLI, macOS deployment helpers and private initialization integration. No changes to guest-readable data, model routing, or other services.
