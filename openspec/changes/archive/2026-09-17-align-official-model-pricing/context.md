# Official pricing alignment (2026-09-17)

## Purpose and sources

This change corrects variant resolution and aligns supported cost estimates with verified public API token rates. These are API retail estimates, not ChatGPT subscription charges. Normative behavior is in this change's specs and the owning api-keys, images-api-compat and proxy-runtime-observability capabilities.

Sources fetched on 2026-09-17:

- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/models/gpt-6-astra
- https://developers.openai.com/api/docs/models/gpt-5.6-sol
- https://developers.openai.com/api/docs/guides/prompt-caching
- https://developers.openai.com/api/docs/guides/flex-processing
- https://developers.openai.com/api/docs/guides/batch

Sol's promotional price is available at least through 2026-11-21. Daybreak aliases are dated assumptions: blue currently points to Sol and red to GPT-5.6 Cyber. Their targets should be reverified with future price updates.

## Decisions and constraints

Build on the existing accounting implementation so corrected rates and unknown-price handling reach both quota settlement and saved request costs. Keep custom-source prices independent.

The official table rounds GPT-5.4 Flex cached input to 0.13. The documented 50% discount applied to 0.25 is exactly 0.125, which is retained for arithmetic. Cyber's model page contains a long-context note but also caps input at 272,000 and its price table has no long-context entries; above that boundary the estimate stays unknown. GPT-5.5 Pro Flex long-context prices are also unpublished.

Historical standard prices for retired Codex/Chat IDs are retained for compatibility; no availability claim follows from retaining a rate. Bare gpt-5.3 has no verified public price. Unverified legacy Codex Fast fields and arbitrary family suffix matches are removed. Ultrafast is an access-controlled preview without a public rate and remains unknown.

## Examples and failure modes

For gpt-5-mini with 100,000 ordinary input and 1,000 output tokens, Standard cost is 0.027 USD. The previous gpt-5 family fallback charged 0.135 USD. A numeric Mini snapshot receives the Mini price; gpt-5-mini-custom remains unknown.

For Astra with 100 input tokens including 40 reads and 20 writes, and 10 output tokens, Standard cost is 0.00119 USD. The 20 writes replace ordinary input tokens and are not added as a second input charge.

Existing stored estimates retain their original amount and pricing version. Missing image modality evidence stays incomplete. A known model on an unpriced tier is marked unknown_pricing, not unknown_model or estimated.

Admission estimates keep the existing bounded token budget (currently capped at 8,192 input and output tokens). They do not prove the eventual upstream context length, especially with server-side conversation history. Unknown requested model/tier is rejected for cost-limited keys; an actual model/tier/context becoming unpriced after admission preserves the already reserved cost allowance and leaves actual billing unknown.

## Operations

No background price fetch or new setting is introduced. Price updates are reviewed code changes. Record the exact package hash and retain the previous executable artifact so code can be rolled back without restoring older business data.
