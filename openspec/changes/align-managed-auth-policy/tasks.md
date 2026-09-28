## Implementation
- [x] Add shared managed/standard policy, typed capabilities, mutation guards, and read-only CLI.
- [x] Expose immutable policy in settings and explain protected controls in the dashboard.
- [x] Switch deployment guard/status to the installed CLI and preserve initialization choices.
- [x] Add API, UI, CLI, deployment, and isolated HTTPS continuity/emergency regression coverage.
- [x] Build and verify installed candidate artifacts and validate OpenSpec.
- [ ] During a separately scheduled rollout, back up and deploy compatible application and wrapper artifacts together, verify acceptance, and record rollback instructions.

## Validation status

- Application/auth/CLI regression: 95 passed. Additional settings/health/reference regression: 103 passed after synchronizing the generated reference and documenting the single-field settings budget increase.
- Frontend: 60 passed; TypeScript and production build passed. macOS helpers: 42 passed. Initialization adapters were separately checked for guest-state preservation.
- Installed candidate: 678 application files match the wheel and source. Real isolated HTTPS kept a stream alive for over two guard periods without a proxy restart; missing password, disabled API authentication and unavailable state all triggered emergency protection.
- Change-level strict OpenSpec validation passes. Global strict validation retains the exact same 22 baseline failures; no new issues.
- Deployment is deliberately deferred. Source publication and isolated validation do not establish production rollout or authenticated live-model acceptance.
