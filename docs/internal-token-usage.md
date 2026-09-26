# Internal token usage

This internal distribution tracks token usage and operational request metrics. It does not calculate monetary estimates for new requests or provide billing controls. Anonymous collector reporting is [retired](telemetry.md).

## What is recorded

Request logs retain reported input, output, cache-read, cache-write and reasoning token evidence, requested and actual models, service tiers, status, latency and generation timing when available. Reasoning remains included in output tokens; cached reads and writes remain input subsets.

New request logs store `cost_usd=null` and `pricing_version=null`. A model without a price is not rejected for pricing availability. Existing token limits and the success/failure settlement rules still apply, including the existing behavior when limited-key usage evidence is missing.

The dashboard shows tokens, requests, cache use, latency, errors and request source IP. It has no monetary summary, currency chart, price editor or monetary-limit control. Reports retain token and timing charts, request-based model/User-Agent distributions, and a CSV with operational and token columns.

## Complete, partial and missing usage

Request logs distinguish complete usage (both input and output reported), partial usage (only some values known), and missing usage. Explicit zero is a valid measurement. An unknown output remains unknown; reasoning tokens are not relabeled as a complete measured output.

Known totals are input plus output, or input plus known reasoning when output is absent. For example, input 100 with missing output and reasoning 20 is shown as partial usage with a known lower bound of 120. Input 100 and output 40, including reasoning 20, is a complete total of 140. Cache reads and writes are input subsets and are not added again. Dashboard cards, trends and reports follow this same known-token rule, including after hourly aggregation. Unknown portions are excluded, so these figures do not guarantee complete actual upstream consumption.

Malformed or negative upstream counters are not valid usage and cannot reduce earlier settled consumption. Normal reservation refunds still apply: reserving 30 for a successful 15-token request refunds the unused 15.

A model-source Responses stream ending in failure or incompleteness is recorded accordingly even if its HTTP status is 200. Known usage is retained in the log; the reservation is released under the existing successful-request quota policy. A stream ending without a terminal response is not considered completed. Reported consumption and API-key limit consumption can therefore differ on failed requests.

When comparing pages, match their time windows and filters. Existing raw-log retention and account visibility rules still apply; this change does not reconstruct unknown historical usage or extend the retention period.

## Existing records and limits

Previously stored amounts, pricing-version strings and source-model prices are preserved. Compatible API fields may return stored historical amounts or their sums; reading them does not reprice old rows or estimate a value for missing amounts. Model-source edits that omit price fields preserve existing values.

New `cost_usd` and price-weighted `credits` API-key rules are rejected with HTTP 400. Old monetary rules remain stored and inactive: they do not block otherwise permitted traffic, participate in settlement, or disappear during token-only rule edits. Ordinary token limits remain enforced. Provider-side account quotas and reset credits remain separate operational capabilities.

The quota planner's old `max_warmup_credits_per_day` monetary budget is inactive and hidden. Mode, allowed times, evidence checks and maximum warmup counts remain in effect. A planner `expected_cost` value is a non-monetary scheduling penalty, not a currency amount.

## Request source IP

`clientIp` is the source address resolved at the service's trusted ingress. Direct traffic uses its socket peer. Forwarded headers are considered only under the existing configured trusted-proxy policy; arbitrary client headers cannot replace the address. This source may be shared by NAT or a reverse proxy and is not a unique device identifier.

The same address is retained through Responses HTTP/SSE/WebSocket and bridge paths, compact and image requests, and auxiliary operations: transcription, file registration/finalization, thread goals, control requests and explicit client warmup. Successful and failed request-log rows preserve it when available. Scheduled warmup and automation have no client and keep null. Historical null values are not inferred or backfilled.

Administrators see the IP column by default and can inspect or search available addresses. Guest responses and searches preserve the existing redaction boundary.

## Data and service boundary

This change requires no migration that deletes data. Historical telemetry columns and migrations remain, and shared encryption keys, accounts, credentials, token history and monetary history are preserved. Two inert pricing entry points remain solely because historical migrations import them; they return `None` and contain no pricing table.

A source checkout and the installed running service are separate. Source validation does not restart, migrate or replace the service. A later deployment must use the project's backup, controlled rollout and independent verification procedure.

---

*Source of truth: [internal-token-usage](https://github.com/627444640/codex-lb/tree/v1.24.1/openspec/specs/internal-token-usage) · [api-keys](https://github.com/627444640/codex-lb/tree/v1.24.1/openspec/specs/api-keys) · [proxy-runtime-observability](https://github.com/627444640/codex-lb/tree/v1.24.1/openspec/specs/proxy-runtime-observability) · [quota-phase-planner](https://github.com/627444640/codex-lb/tree/v1.24.1/openspec/specs/quota-phase-planner)*
