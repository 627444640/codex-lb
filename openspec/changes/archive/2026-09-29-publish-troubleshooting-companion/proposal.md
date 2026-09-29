# Publish the paired troubleshooting component

## Why
The administrator requested a feature branch, a local merge into v1.24.3 and publication to their repository. The dashboard integration depends on an independently running monitor whose source previously existed only outside Git. Publishing the dashboard alone would leave an incomplete source delivery.

## What Changes
- Include portable monitor runtime, static assets, dependency locks and synthetic tests under `deploy/status-monitor/`.
- Document isolated setup and the administrator-only connector; exclude runtime state, credentials, databases, captured logs and local diagnostic reports.
- Replace host-specific seed addresses with clearly labelled example addresses in the distributable component. Existing runtime guide data is not modified.
- Add a dedicated companion test target and retain separate deployment and real-model acceptance boundaries.

## Impact
Source distribution and validation only. The optional component is not started by the base LB install. No production service, credential, database, port or LaunchAgent is changed.
