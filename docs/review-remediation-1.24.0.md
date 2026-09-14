# 1.24.0 review: all eleven repairs

This maintenance branch contains all eleven verified repairs. Eight are in
the application; three are in portable macOS operator tooling. The macOS
tooling is published as source under `deploy/macos/`. Actual deployment
configuration and runtime files are not included.

The owning specifications are [deployment installation](../openspec/specs/deployment-installation/spec.md),
[API keys](../openspec/specs/api-keys/spec.md),
[admin authentication](../openspec/specs/admin-auth/spec.md),
[Responses compatibility](../openspec/specs/responses-api-compat/spec.md),
[HTTP ingress limits](../openspec/specs/http-ingress-limits/spec.md),
[proxy admission](../openspec/specs/proxy-admission-control/spec.md) and
[query caching](../openspec/specs/query-caching/spec.md).
The [application verification record](../openspec/changes/archive/2026-09-14-remediate-deployed-1-24-review/verification.md)
records the prior complete application validation.

| ID | Repaired behavior | Primary implementation |
|---|---|---|
| R01 | Bound zstd declared output, decoder window and streamed output before excessive allocation. | [request_decompression.py](../app/core/middleware/request_decompression.py) |
| R02 | Wait for bounded LaunchAgent removal, process-group exit and listener closure before maintenance; retain incomplete-stop evidence across retries. | [manage.py: stop](../deploy/macos/bin/manage.py) |
| R03 | Restore a verified backup when the current database is damaged or absent; first preserve separate, explicitly unverified raw recovery material. | [manage.py: restore](../deploy/macos/bin/manage.py) |
| R04 | Reject unsupported credits limits at creation/update and admission; retain supported token/cost limits. | [API key service](../app/modules/api_keys/service.py) |
| R05 | Bind dashboard cookies to the credentials actually verified and validate them at every consumer; preserve TOTP upgrade boundaries. | [dashboard auth](../app/modules/dashboard_auth/service.py) |
| R06 | Preserve independent tool calls with distinct nonblank call IDs and their outputs. | [tool_call_dedupe.py](../app/modules/proxy/tool_call_dedupe.py) |
| R07 | Bound request and shared event-queue memory; fail overflowing delivery without blocking siblings or losing upstream settlement. | [http_bridge_event_queue.py](../app/modules/proxy/http_bridge_event_queue.py) |
| R08 | Run bcrypt outside the event loop with two permits and cancellation-safe ownership. | [dashboard auth](../app/modules/dashboard_auth/service.py) |
| R09 | Trim usage-history caches as the requested window advances; bound retention and protect concurrent invalidation. | [usage repository](../app/modules/usage/repository.py) |
| R10 | Drain child output through EOF or a two-second deadline, retaining final diagnostics, redaction and exit status. | [supervise.py](../deploy/macos/bin/supervise.py) |
| R11 | Measure current macOS RSS so admission can recover after memory is released. | [memory_monitor.py](../app/core/resilience/memory_monitor.py) |

The additional admin/guest login-form error-handling fix is also included.

See [macOS operator tooling](macos-maintenance.md) for the local runtime
contract and commands. This branch remains based on upstream 1.24.0; it does
not replace the repository's newer main branch or install anything into a
running service. The application wheel contains application fixes; macOS
operator scripts are separate source files in this repository/source archive.
