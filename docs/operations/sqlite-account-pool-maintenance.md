# SQLite account-pool maintenance for 1.24.0

This is the `sqlite-reliability-20260921` maintenance source line. It is based on
public commit `9e932343a003d8caf229ef8e4b0d5e045705d0ea` and retains its accounting,
pricing, generation-timing and earlier review fixes. It does not replace the
newer beta version on `main`.

Owning specifications: [Responses compatibility](../../openspec/specs/responses-api-compat/spec.md),
[account routing](../../openspec/specs/account-routing/spec.md),
[database backends](../../openspec/specs/database-backends/spec.md), and the
[active maintenance change](../../openspec/changes/harden-local-account-pool-recovery/proposal.md).

## Source and release identity

All package, application, frontend, Helm and lockfile version fields remain
`1.24.0`. Identify a maintenance build by its Git commit and artifact SHA-256,
not by that package version alone. This source publication does not create a
release, tag, automatic deployment or database-backend migration. Version bumps
and release notes continue through the repository's release process.

The reference beta snapshot is `69f128afcbc616d9f8e924ca6583f7031d75cf82`.
Selected backports, adapted to the existing 1.24.0 time/scheduling interfaces:

| Concern | Reference commit |
| --- | --- |
| Fenced full-context stale-anchor recovery | `a347912b8334af52133bfc4436381fb78afb8888` |
| Settle API-key reservations before account health | `f9965fac8fafd378e658b510631f821c7db314f0` |
| Bounded accepted/output-free capacity recovery | `dafc1a21de88cea0c94124e964a02a5d046cb8bb` |
| Preserve hard sticky owners during recovery | `ae330ba9edd71a93a11151b01446a025e9d5db59` |
| Fresh-admission overload backoff | `7b0f717501c20b1a7be5534246539d88a8e058e4` |
| Sustained isolation and recent-error weighting | `3de4be2aa9221db6a7137daca4c14c5d2a1ff639` |
| Retain soft owners and stabilize temporary substitutes | `e54d97433eb0d71501cf7d46b81c6e13aed9f9b4` |
| Confirm recovery using the actual blocked quota window | `3d501ac5eae2ec3201d3d0a98b961793db519a27` |
| Bound detached-session cleanup lock waits | `58c6a28f24b8672830ca4bdda911fe6f191de47e` |

AnyIO is explicitly required at `>=4.14.0`; the lockfile and validation
environment use 4.14.0. Lock acquisition and release stay in the same task.
The complete beta authentication/schema migration and transport replacement
are outside this maintenance line.

## Recovery and routing boundaries

A rejected stale response anchor is recoverable only from a verified complete
replacement body with the required operation/owner/admission fences. A delta
plus `previous_response_id` is not complete input. File-, response- and
session-owned requests keep their hard ownership constraints.

Accepted lifecycle events without output can qualify for one bounded capacity
recovery. The client retains one response identity, one created event and one
terminal result. Visible text, reasoning/tool output, billed output or ambiguous
delivery blocks unsafe replay. This does not make every `stream_incomplete`
recoverable and does not extend replay to arbitrary direct HTTP/SSE EOFs.

Three overload rejections within a 120-second window trip account backoff.
Persistent trips reach a default 1,800-second isolation interval at level three.
Ordinary successes do not erase the overload window. Fresh selections prefer
eligible siblings; if that filter cannot select an alternative, the original
pool remains available. Hard ownership and policy gates remain authoritative.

During isolation a recoverable soft owner retains its mapping while an eligible
thread-stable substitute serves the turn. TTL freshness is maintained where the
request has mutation authority. Retention of a `reauth_required` mapping does
not make the account selectable, refresh credentials or change its status.

Operators can disable sustained isolation with
`CODEX_LB_PROXY_OVERLOAD_ISOLATION_SECONDS=0`, or disable the bounded recent-error
weight discount with `CODEX_LB_PROXY_ACCOUNT_ERROR_RATE_WEIGHTING_ENABLED=false`.
These independent rollback controls are the reason they are settings rather
than hardcoded deployment policy. See the [settings reference](../reference/settings.md).

Quota reset recovery requires post-block evidence anchored to the actual blocked
window. Ambiguous/stale transitions, another exhausted live window, and newer
concurrent restriction markers cannot be overridden.

## SQLite structure and rollback

The existing custom timing/pricing lineage is retained. The new merge revision
`20260921_000000_merge_local_timing_and_stale_recovery` joins
`20260915_000000_add_request_log_output_timing` with
`20260821_000000_add_retry_circuit_admission_generation`.

A downgrade to the old timing head alone leaves the new admission-generation
branch present. Offline rehearsal verified that downgrading to the old timing
head and then targeting
`20260821_000000_add_retry_circuit_admission_generation@-1` restores the exact old
head. Use migration code that knows both branches, stop business writes, and
check integrity, data and revision heads before returning an old application to
service. Do not restore an old rehearsal snapshot over newer live records.

## Private database/key rehearsal

`tools/sqlite_recovery_rehearsal.py` uses the SQLite online backup API with a
read-only source, keeps the matching encryption key, refuses existing outputs,
creates owner-only files/directories, restores a strict archive member set and
checks integrity and credential decryptability without starting the application.

```sh
python tools/sqlite_recovery_rehearsal.py \
  --source-database "$HOME/.codex-lb/store.db" \
  --source-key "$HOME/.codex-lb/encryption.key" \
  --output /private-backups/new-rehearsal-directory
```

The output contains sensitive account material and must remain private. It is a
database/key-only format, not the whole-service archive expected by separate
operator restore tools. Successful decryption proves the database/key pairing;
it does not prove upstream login validity. A deployment still needs a fresh
whole-service backup, exact old application/dependencies and a tested rollback.

## Bounded observations and migration triggers

```sh
python tools/sqlite_reliability_observer.py \
  --database "$HOME/.codex-lb/store.db" \
  --backend-log /private-logs/backend.log \
  --output /private-observations/new-observation.json \
  --window-hours 24 --samples 3 --interval-seconds 5
```

The observer generates no model requests. It reports status/kind denominators,
successful-normal latency and first-output sample counts, file sizes, an hourly
rollup watermark/tail, and explicitly observed log markers. Successful-request
percentiles exclude failures/cancellations. Log events are not distinct request
counts. Its UTC timestamp parser expects the application's ISO `...Z` marker;
other log formats/rotated files need a separately verified collection method.

`sqlite_writer_wait` reports acquisitions taking at least 100 ms in the local
serialized write section, including failed/cancelled acquisitions. It is not
all SQL wait time or cross-process lock time. Rollup tails are not all background
queues. Missing samples remain unknown. This tool is bounded, not a scheduler,
continuous monitor, capacity benchmark or notification service.

Keep SQLite until measured needs justify a migration evaluation:

| Trigger | Required evidence |
| --- | --- |
| Multiple machines/replicas must write shared business data | Confirmed writers, deployment topology and shared-state requirements |
| Persistent lock/writer timeouts still affect requests after optimization | Duration/frequency, request completion/first-output impact, and results of shorter transactions/index/background-work changes |
| Logs/statistics/refresh jobs cause sustained heavy writes | Actual write sources, duration, queue/resource trends; request counts alone are insufficient |
| Replication, centralized permissions or point-in-time recovery is required | Confirmed operational/recovery requirements and the existing system's gap |

Adding Pro accounts or seeing upstream overload/session errors does not alone
prove a database bottleneck. A knowledge service may retain its separate
PostgreSQL database and consume authenticated management APIs; generic knowledge
SQL tools should not directly manage LB credentials or its runtime directory.
When an evidence-backed trigger appears, notify the operator to evaluate
migration. Documentation alone does not install that notification mechanism.

## Validation boundary

Regression coverage uses synthetic upstreams and isolated databases. It includes
stale-anchor rejection, output-free replay refusal/allow cases, account ownership,
settlement, cancellation, stable substitutes, quota-window evidence, database/key
restoration, writer-wait cancellation and existing generation-timing behavior.

Production restart, authentication, real two-account failover and throughput
remain separate acceptance work. A private offline rehearsal is not a model
capacity test. Private deployment counts, credentials, logs and host-specific
reports are intentionally absent from this public source record.
