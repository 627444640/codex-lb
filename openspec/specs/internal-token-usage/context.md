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
