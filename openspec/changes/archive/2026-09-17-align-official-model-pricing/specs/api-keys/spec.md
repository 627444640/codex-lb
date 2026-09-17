## MODIFIED Requirements

### Requirement: GPT-5.6 usage cost pricing matches the current published rates

When computing API-key usage, request-log, reservation, or aggregate cost for the canonical GPT-5.6 models, the system MUST use these USD-per-1M-token rates
for input, cached input, and output:

| Model | Standard | Fast/priority | Flex | Standard long context |
| --- | --- | --- | --- | --- |
| `gpt-5.6-sol` | `4 / 0.40 / 20` | `8 / 0.80 / 40` | `2 / 0.20 / 10` | `8 / 0.80 / 30` |
| `gpt-5.6-terra` | `2 / 0.20 / 12` | `4 / 0.40 / 24` | `1 / 0.10 / 6` | `4 / 0.40 / 18` |
| `gpt-5.6-luna` | `0.20 / 0.02 / 1.20` | `0.40 / 0.04 / 2.40` | `0.10 / 0.01 / 0.60` | `0.40 / 0.04 / 1.80` |

The existing `priority` and `fast` service-tier aliases MUST use the
Fast/priority rates. Standard long-context rates MUST apply only when input
tokens exceed 272,000. Fast and Flex long-context pricing MUST apply twice their short-context input
and cached-input rates and 1.5 times their short-context output rates. Model aliases with a
numeric dated snapshot suffix MUST resolve to the corresponding canonical table
entry.

Reported cache-write tokens MUST be priced at 1.25 times the effective
input rate and MUST be subtracted alongside cached reads from ordinary
input tokens. Unreported cache writes MUST remain unknown in request logs.
Sol rates are the verified promotional table as of 2026-09-17; persisted
estimates MUST retain a pricing version. Batch service behavior is outside
this proxy contract.

#### Scenario: Terra standard usage uses the current rate

- **WHEN** a standard-tier `gpt-5.6-terra` request has 200,000 input tokens and 1,000,000 output tokens
- **THEN** the token cost is `$12.40`

#### Scenario: Luna Fast and Flex usage use their tier rates

- **WHEN** a `gpt-5.6-luna` request has 200,000 input tokens, 100,000 cached input tokens, and 1,000,000 output tokens
- **AND** the request uses `priority` or `fast`
- **THEN** the token cost is `$2.444`
- **WHEN** the same usage uses `flex`
- **THEN** the token cost is `$0.611`

#### Scenario: Terra standard long-context usage uses the current long-context rate

- **WHEN** a standard-tier `gpt-5.6-terra` request has 300,000 input tokens, 50,000 cached input tokens, and 100,000 output tokens
- **THEN** the token cost is `$2.82`

#### Scenario: Versioned aliases use canonical GPT-5.6 pricing

- **WHEN** the requested model is `gpt-5.6-luna-2026-07-13`
- **THEN** cost accounting resolves it to the `gpt-5.6-luna` price entry

## ADDED Requirements

### Requirement: Published variants have independent verified rates

The system MUST use the following Standard USD-per-million input/cached-input/output rates: GPT-5 Mini 0.25/0.025/2, GPT-5 Nano 0.05/0.005/0.4, GPT-5 Pro 15/unavailable/120, GPT-5.2 Pro 21/unavailable/168, GPT-5.5 Cyber and GPT-5.6 Cyber 12.5/1.25/75, and chat-latest 5/0.5/30. GPT-5.6 Cyber cache writes MUST use 15.625 per million. GPT-5 Mini Fast MUST use 0.45/0.045/3.6; Mini and Nano Flex MUST use half their Standard rates.

#### Scenario: Mini is not priced as the full model
- **WHEN** gpt-5-mini reports 100,000 ordinary input and 1,000 output tokens on Standard
- **THEN** its cost estimate is 0.027 USD

### Requirement: Default price resolution does not guess variant prices

The system MUST resolve exact registered model IDs, their numeric YYYY-MM-DD snapshots and explicitly published compatibility aliases. It MUST NOT match arbitrary suffixes or unknown model families to a shorter model name. The gpt-5.6 and gpt-daybreak-blue-latest aliases MUST resolve to Sol; gpt-daybreak-red-latest MUST resolve to GPT-5.6 Cyber. A model or service tier without verified public pricing MUST remain unknown in cost estimates, including bare gpt-5.3 and ultrafast.

#### Scenario: Unknown variant remains unpriced
- **WHEN** gpt-5.7 or gpt-5-mini-custom is reported without a custom price
- **THEN** no built-in cost estimate is fabricated

#### Scenario: Numeric snapshot keeps its own variant rate
- **WHEN** gpt-5-mini-2025-08-07 is reported
- **THEN** it uses the Mini rate, not the GPT-5 rate

#### Scenario: Unpublished tier remains unknown
- **WHEN** a Sol response reports service_tier ultrafast
- **THEN** its API cost estimate is unknown

### Requirement: Unknown pricing cannot bypass cost limits

For requests subject to a cost_usd limit, admission MUST reject an unpriced requested model or service tier with pricing_unavailable instead of admitting it as free, using the existing bounded input/output budget for context-sensitive admission estimates. A custom model source MUST use its own verified configured price for admission. If an admitted request's actual model, tier or context length has no verifiable final cost, successful settlement MUST retain that request's previously reserved cost-limit amount while leaving its actual cost unknown. Token and request limits MUST settle from their actual usage, and repeated settlement MUST remain idempotent. An explicit verified zero cost MUST remain distinct from unknown cost and MUST release the cost reservation normally.

#### Scenario: Unknown requested price is rejected before forwarding
- **WHEN** a cost-limited API key requests Sol on ultrafast without a configured source price
- **THEN** admission returns pricing_unavailable and does not call upstream

#### Scenario: Upstream changes to an unpriced model
- **WHEN** a request reserved a known cost budget and the successful upstream response reports an unpriced actual model
- **THEN** settlement retains the original cost-limit reservation as a conservative allowance
- **AND** actual cost stays unknown, token counts settle to actual usage, and another settlement changes nothing

#### Scenario: Explicit zero cost releases the allowance
- **WHEN** a request has an explicit verified final cost of zero
- **THEN** the cost reservation is released rather than retained as unknown
