## Why

The public 1.24.0 remediation branch contains eight application fixes. R02,
R03 and R10 were implemented and tested in private macOS deployment tooling,
so users cannot obtain all eleven fixes from the public branch. Publish the
reusable tooling with synthetic examples, while keeping actual deployment
configuration, credentials, state, reports and withdrawn history private.

## What Changes

- Add portable macOS maintenance and supervisor source under `deploy/macos/`.
- Preserve complete shutdown, damaged-state restore and bounded final-log
  draining, with their regression coverage.
- Replace machine-specific paths and identifiers with runtime configuration
  or portable defaults; document the required local runtime layout.
- Ignore private runtime files and verify the public candidate contains only
  allowlisted source, synthetic examples, tests and documentation.
- Record an eleven-item repair map and publication verification.

## Impact

- Affected specification: `deployment-installation`.
- Affected code: standalone `deploy/macos/` tooling and its validation target.
- The existing application fixes remain unchanged. Production installation,
  a main-branch merge and package-registry publication are outside this change.
