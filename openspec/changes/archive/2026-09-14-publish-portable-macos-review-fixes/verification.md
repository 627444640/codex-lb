# Portable macOS repair publication verification

## Result and scope

The public maintenance source now contains all eleven review repairs. R02,
R03 and R10 are available under `deploy/macos/`; the eight application repairs
and the login-form fix remain unchanged from the previously tested public
application tree (`e16af457`). See the [complete repair map](../../../../docs/review-remediation-1.24.0.md)
and [operator contract](../../../../docs/macos-maintenance.md).

The operator source contains four executable/support files, three regression
and integration files, three freshly authored synthetic examples and two
scoped rule files. It contains no actual deployment configuration, credentials,
databases, certificates, logs, backups or private audit reports. Optional
personal admin/client helper scripts are not published or required for new
backups; older backups containing those files remain accepted.

## Executed checks

| Check | Result |
|---|---|
| Standalone regressions on Python 3.12 | 42 passed |
| New Makefile/CI entry on Python 3.13 | 42 passed |
| Python 3.13 with ResourceWarning enabled after fixture cleanup | 42 passed, no ResourceWarning |
| Real temporary macOS LaunchAgent | Stop completed in 0.499 seconds; final write preceded return; group absent; job unloaded; final log retained; pending record cleared; temporary directory removed |
| Repository Ruff check and format check | Passed |
| Application type checking and proxy architecture checks | Passed |
| OpenSpec validation | Standard full-spec validation: 57 passed; change and deployment-installation strict validation passed |
| Independent extraction review | R02/R03/R10 critical function ASTs match the previously validated corrected implementation |
| Independent privacy review | Passed for the 12 public deployment files, operator documents and change artifacts |
| Ignore-policy probes | 14 representative private/unapproved paths ignored |
| Application comparison | No changes to application, frontend, application tests, config package or uv.lock relative to the tested public base |

The imported tests preserve all 28 manager regression cases and 10 relevant
common/supervisor cases, plus four portability tests. They cover delayed final
writes after listener closure, incomplete-shutdown retries, damaged or absent
databases, raw snapshot failures, rollback failures, archive validation,
output bursts, unterminated final lines, redaction and descendant-held pipes.
Portability coverage adds config-free help and wrapper relocation, configured
Python/current-home LaunchAgent paths, uv discovery/failure, and optional
ancillary backup compatibility.

The initial restricted test run could not bind an ephemeral loopback socket;
the isolated test was rerun with the required local-process permissions and
passed. Python 3.13 exposed unclosed SQLite fixture connections; the fixtures
now explicitly close connections while preserving transaction commits and
assertions. The final warning-enabled run is clean.

## Publication boundaries

Only allowlisted source, tests and examples are published. The existing
pre-push privacy guard remains enabled; the public branch does not merge
withdrawn deployment history. Source and Git-history checks precede the push.
The three macOS fixes are operator source in the repository/source archive;
they are not installed by the application wheel.

The full application/frontend/PostgreSQL suite results remain in the earlier
application verification record. Those suites were not redundantly rerun for
this source-only extraction: application bytes are unchanged. The standalone
tools retain their Python 3.12 contract and dedicated lint/executable tests;
application type checking excludes the standalone deployment directory.

No production service was started, stopped, reconfigured or upgraded. No
main-branch merge, package-registry release, real account traffic, remote HTTPS
rollout or long-running load test is part of this publication.
