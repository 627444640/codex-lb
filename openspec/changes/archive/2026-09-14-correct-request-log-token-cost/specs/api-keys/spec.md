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
version or snapshot suffix MUST resolve to the corresponding canonical table
entry.

Reported cache-write tokens MUST be priced at 1.25 times the effective
input rate and MUST be subtracted alongside cached reads from ordinary
input tokens. Unreported cache writes MUST remain unknown in request logs.
Sol rates are the verified promotional table as of 2026-09-14; persisted
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
