# Internal token usage

## Decision

This internal distribution records usage for operations and token limits. It does not estimate currency amounts, use source prices to admit traffic, or expose billing controls. This is fixed behavior, not a new optional flag. Anonymous reporting is retired under the separate [telemetry specification](../telemetry/spec.md).

## Accounting and compatibility

Keep reported input, output, cached-read, cache-write and reasoning token evidence. Cached reads and writes are subsets of input; reasoning is included in output and must not be counted twice. Preserve existing success/failure settlement and token reservation invariants. Missing price information never creates a pricing-availability rejection. Missing token usage still follows the existing limited-key usage-evidence contract.

New request logs store null `cost_usd` and `pricing_version`. Compatible APIs may return existing stored historical costs or sums of those stored values; reads do not estimate, reprice, backfill or rewrite them. Legacy monetary records are historical data, not an active billing configuration or a promise of free upstream service.

For example, a key with an exhausted old `cost_usd` limit and an available token limit remains governed by its token limit. A token-only limit edit preserves the old monetary row, current value and reset time without activating it. New `cost_usd` or price-weighted `credits` rules are rejected atomically. Real upstream account quotas and reset credits are separate provider-side capacity information and retain their behavior.

Model-source edits omit price fields. Omission preserves any existing source-model prices instead of clearing them. The dashboard shows tokens, requests, cache use, latency, error metrics and trusted client IP, without monetary totals, price forms or monetary-limit controls. Existing response fields may remain for compatibility.

## Source IP and data safety

Reuse nullable `request_logs.client_ip`, its existing index, trusted-proxy resolver and signed bridge context. Explicit client warmup retains its initiating address. Scheduled warmup and automation have no client and keep null. Source IP is the address observed at the service's trusted ingress; NAT and reverse proxies can make it differ from a device's private interface address. Do not infer addresses for historical nulls. Admins can view and search IP; guest redaction remains intact.

No data-removal migration or price backfill is required. Existing migrations, accounts, credentials, request history, consent values, encryption keys and monetary records remain in place. Test fixtures and build artifacts are isolated from production. Source completion and the separate installed service deployment must be reported independently.

See [requirements](spec.md), [API keys](../api-keys/spec.md), [observability](../proxy-runtime-observability/spec.md), and the [change proposal](../../changes/internal-token-only-usage/proposal.md).

## Historical migration imports

Historical migration `20260325` imports `get_pricing_for_model` and `calculate_cost_from_usage`. The internal build retains these two inert compatibility entry points, both returning `None`, so the unchanged migration graph remains importable for fresh databases. They contain neither a ratebook nor a calculation path. Their presence does not restore billing.

## Accounting evidence and partial usage

Use upstream non-negative integer counters as evidence. Invalid values are unknown rather than measured zero and cannot refund consumption from earlier requests. This does not forbid negative reservation adjustments: reserving 30 for a valid 15-token request must refund the unused 15, while settling that reservation twice remains a no-op.

Request-log usage status is derived from raw nullable fields: complete requires input and output (including explicit zero); partial means only some of input/output/reasoning are known; missing means none are known. A known total combines reported input with output, falling back to known reasoning only when output is absent. Cache subsets and reasoning are never counted twice. For example, input 100, missing output and reasoning 20 gives a known lower bound of 120, with output still unknown. Input 100 and output 40 (including reasoning 20) gives a complete total of 140. Dashboard cards/trends use the same rule for raw and folded data through the existing output-or-reasoning measure, without a historical rewrite.

Aggregate figures describe known reported usage; they cannot prove the total consumed on requests without usage. Window, filters, soft deletion and raw-log retention can still affect cross-page comparisons. This change does not redesign long-term report retention or recover historical missing usage.

Model-source Responses outcome is independent of transport status. HTTP 200 followed by response.failed remains a failed request. Failed/incomplete/unterminated responses release the reservation under the existing success-only limit policy while retaining valid reported usage in logs. Consequently observed consumption and successful-request quota remain distinct metrics. No route, account selection or pricing policy changes are implied.
