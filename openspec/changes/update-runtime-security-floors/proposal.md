## Why

The current main-line Docker gate reports seven fixed High/Critical findings in aiohttp, Brotli, certifi and urllib3. Their locked versions are below the scanner's fixed versions, preventing unrelated proxy repairs from meeting the existing security gate.

## What Changes

- Raise the four dependency floors to the verified patched versions and update their lock entries plus aiohttp's required yarl version.
- Preserve vulnerability scanning and its severity thresholds.
- Run the HTTP-client/proxy compatibility tests and require a fresh image scan.

## Capabilities

No application-level contract changes. This dependency-metadata maintenance follows the existing certifi-floor change's `skip_specs: true` convention.

## Impact

`pyproject.toml`, `uv.lock` and this maintenance record. No schema, operator setting, proxy routing or wire-format changes are intended.
