## Why

The current main-line Docker gate reports seven fixed High/Critical findings in Python networking libraries, and the Rust advisory gate reports ten findings in TLS, async I/O and compression dependencies. Their locked versions prevent unrelated proxy repairs from meeting the existing security gates.

## What Changes

- Raise the four dependency floors to the verified patched versions and update their lock entries plus aiohttp's required yarl version.
- Update the native Rust TLS/async runtime pins and compression dependency closure to patched compatible releases.
- Preserve vulnerability scanning and its severity thresholds.
- Run the HTTP-client/proxy compatibility tests and require a fresh image scan.

## Capabilities

No application-level contract changes. This dependency-metadata maintenance follows the existing certifi-floor change's `skip_specs: true` convention.

## Impact

`pyproject.toml`, `uv.lock`, `Cargo.toml`, `Cargo.lock` and this maintenance record. No schema, operator setting, proxy routing or wire-format changes are intended. Native protocol/build tests remain required.
