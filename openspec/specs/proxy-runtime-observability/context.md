# Proxy Runtime Observability Context

## Purpose and Scope

This capability defines what operators should be able to see in the live server console while debugging proxy traffic.

See `openspec/specs/proxy-runtime-observability/spec.md` for normative requirements.

## Decisions

- **Timestamps are always on:** timestamped console logs are a baseline operator need, not a debug-only feature.
- **Request tracing is opt-in:** outbound request summary and payload tracing remain configurable because payload logs can be noisy or sensitive. Since issue #1340 phase 1 the switch is the single `CODEX_LB_TRACE` comma-separated channel list (`shape`, `shape_raw_cache_key`, `payload`, `service_tier`, `upstream_summary`, `upstream_payload`); empty default = all off. It is an incident-debugging knob for interactive use only.
- **Error logs must be correlated:** request id, endpoint, status, code, and message are the minimum useful fields for debugging 4xx/5xx failures.
- **Prewarm observability is outcome-only:** the Codex HTTP-bridge prewarm canary experiment finished, so its bucket/cohort dimensions were retired (issue #1340 phase 4). The `codex_lb_http_bridge_prewarm_total` counter is labelled by `outcome` only, request logs record `prewarm_status` / `prewarm_latency_ms` (statuses: `not_applicable`, `skipped`, `success`, `timeout`, `error` — `canary_miss` no longer occurs), and the legacy `prewarm_canary_bucket` / `prewarm_eligible_reason` request-log columns stay declared but unwritten for one release for rolling-upgrade safety; the Alembic drop revision ships next release (see the next-release queue in `openspec/specs/deployment-installation/context.md`).
- **TTFT datasource selection stays in Grafana:** the Helm chart packages the
  TTFT dashboard but does not provision a PostgreSQL datasource or its
  credentials. The visible, single-select `DS_SQL` variable keeps
  installation-specific datasource UIDs out of chart values while routing all
  four SQL panels through one explicit selection.

- **Generation timing uses upstream observation:** completion is frozen before settlement and cleanup. TPS uses separately observed non-reasoning output timing, requires at least two chunks and a 100 ms window, and remains an estimate. Legacy samples are labeled and excluded from qualified daily medians; missing medians remain null. The reproduced failures and validation are documented in `openspec/changes/archive/2026-09-15-correct-generation-timing/context.md`.

## Operational Notes

- Use request ids to correlate inbound proxy logs, outbound upstream traces, and client-visible failures.
- Prefer summary tracing in normal debugging sessions; enable payload tracing only when the exact normalized outbound request matters.
- For direct compact `5xx` failures, look for `proxy_compact_failure` alongside `upstream_request_complete`; together they show the compact failure phase, failure detail, exception type, retry metadata, and affinity source.
- After the Grafana sidecar imports the TTFT dashboard, select the ordinary
  PostgreSQL datasource that points to the codex-lb database from the visible
  **PostgreSQL** dropdown. A datasource registered only as a frontend runtime
  plugin is not listed by Grafana's datasource variable.
- Timeout invariant violation logs describe startup `Settings` and imported
  constant validation only. They intentionally avoid request-scoped overrides,
  runtime-derived effective timeout values, payloads, API keys, access tokens,
  raw affinity keys, account emails, and other high-cardinality identifiers.


## Token evidence and historical amounts

The internal distribution records tokens and model/tier metadata without estimating money. New `cost_usd` and `pricing_version` values are null. Cached reads and writes remain input subsets; reasoning remains included in output. Failed terminal usage remains diagnostic evidence without weakening success-only settlement.

Stored historical amounts and price-version strings remain readable for response compatibility and are not repriced. A null old cost stays null. Monetary fields are not shown in the internal dashboard. See [internal token usage](../internal-token-usage/spec.md).

## Client source addresses

Use the existing trusted-proxy resolver at each client entry, then pass its result explicitly through the service and log writer. Six auxiliary operation families now follow the same contract as Responses: transcription, file registration/finalization, thread goals, control operations and explicit warmup. Purely scheduled work has no client address. HTTP bridge forwarding retains its authenticated original-IP context. Arbitrary forwarded headers from untrusted peers cannot override the socket address.

An IP describes the observed network source, which may be a NAT or trusted ingress address rather than a device's private interface. Admins can inspect it; guest views and search keep the existing redaction boundary. No historical IP backfill or additional migration is needed.

## Internal canonical SSE observation

The internal streaming observer preserves the existing nonempty-content sample
contract while recognizing a bounded flat-object subset without JSON-object
allocation. Empty strings remain unobserved; escaped/non-ASCII nonempty strings
still count. Unknown, duplicate, escaped-key, nested, oversized or unusual numeric
shapes use the existing decoder, retaining its error behavior. First-output,
TTFT, terminal timing and the 100 ms/two-nonempty-chunk policy are unchanged.

For example, reasoning at 125 ms, empty text at 200 ms, and actual output at 250
and 750 ms still yield TTFT=125 ms, first output=250 ms and output count=2.
Benchmarks show an observation-only benefit for supported frames and a small
classification cost on fallback frames; they are not production speed measurements.
See `openspec/changes/archive/2026-09-28-optimize-internal-stream-output-observation/verification.md`.

This independent `feat` work is intended for later integration with status-page
settings into internal v1.24.3. Combined integration and deployment are separate
acceptance steps; the feature introduces no migration or release-version change.
