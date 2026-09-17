## ADDED Requirements

### Requirement: Cost reservations cover cache-write and image modality rates
Within a request's bounded input/output budget, admission MUST reserve the maximum applicable input rate when cache writes or image modality are not yet known. Final successful settlement MUST use reported cache writes and actual model identity, and MUST preserve explicit image cost overrides. Settlement MUST remain idempotent and MUST NOT convert an image cost marked unknown into host-model charges.

#### Scenario: Cache writes exceed ordinary input rates
- **WHEN** admission estimates 10,000 input tokens for a model with a 1.25-times cache-write rate
- **THEN** its cost reservation covers all 10,000 tokens being cache writes
- **AND** final settlement adjusts the reservation to the reported input partition exactly once

#### Scenario: Image modality is not known at admission
- **WHEN** an image request has a bounded input/output token budget
- **THEN** reservation uses the upper bound of the model's text and image token rates
- **AND** final costs use the image usage evidence instead of this admission estimate

### Requirement: Verified Astra and long-context pricing
The system MUST recognize Astra and its versioned aliases with standard short-context USD-per-million rates of 10 input, 1 cached input, 12.5 cache write, and 50 output. For Astra requests above 272,000 input tokens, input and cache rates MUST double and output rates MUST increase by 1.5 times. Fast MUST use twice the respective standard rates and Flex MUST use half. GPT-5.5 standard long-context pricing MUST apply the published 2-times input and 1.5-times output uplift, and GPT-5.4-mini Fast MUST use twice its standard rates. Unverified model aliases MUST NOT be guessed.

#### Scenario: Astra cache writes are separately priced
- **WHEN** an Astra request reports 100 input tokens, 40 cached reads, 20 cache writes, and 10 output tokens
- **THEN** ordinary input is 40 tokens and its standard short-context estimate is 0.00119 USD

#### Scenario: Auto-review has no verified price
- **WHEN** a response reports the model codex-auto-review and no custom price exists
- **THEN** builtin cost accounting returns unknown

### Requirement: Published variants have independent verified rates

The system MUST use the following Standard USD-per-million input/cached-input/output rates: GPT-5 Mini 0.25/0.025/2, GPT-5 Nano 0.05/0.005/0.4, GPT-5 Pro 15/unavailable/120, GPT-5.2 Pro 21/unavailable/168, GPT-5.5 Cyber and GPT-5.6 Cyber 12.5/1.25/75, and chat-latest 5/0.5/30. GPT-5.6 Cyber cache writes MUST use 15.625 per million. GPT-5 Mini Fast MUST use 0.45/0.045/3.6; Mini and Nano Flex MUST use half their Standard rates.

#### Scenario: Mini is not priced as the full model
- **WHEN** gpt-5-mini reports 100,000 ordinary input and 1,000 output tokens on Standard
- **THEN** its cost estimate is 0.027 USD

### Requirement: Default price resolution does not guess variant prices

The system MUST resolve exact entries in the validated active catalog, their numeric YYYY-MM-DD snapshots and explicitly published compatibility aliases. It MUST NOT match arbitrary suffixes or unknown model families to a shorter model name. The gpt-5.6 and gpt-daybreak-blue-latest aliases MUST resolve to Sol; gpt-daybreak-red-latest MUST resolve to GPT-5.6 Cyber. A model or service tier without verified public pricing MUST remain unknown in cost estimates, including ultrafast and bare gpt-5.3 when no validated exact catalog entry exists.

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
