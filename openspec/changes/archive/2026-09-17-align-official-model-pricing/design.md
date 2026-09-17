## Context

The accounting and output-timing implementation already records usage partitions and pricing provenance. See proposal.md for the remaining rate-resolution and quota-settlement problems.

## Goals / Non-Goals

Goals: verified variant prices, honest unknown-cost status and cost-limit enforcement without guessed charges.

Non-goals: rewriting historical bills, adding Batch proxy support, changing credentials or adding a network dependency to request-time pricing.

## Decisions

- Keep explicit model entries and bounded numeric snapshot aliases. Unknown variants do not inherit a shorter model's price.
- Make rate selection return no estimate when a tier or long-context combination has no verified public price. Keep the existing disjoint cache-read/write and image-modality calculations.
- Retain verified historical Standard entries for compatibility, but remove the unverified bare gpt-5.3 entry and unverified legacy Codex Fast rates. A price entry does not promise model availability.
- Preserve exact fractional rates where the public table rounds a documented 50% Flex discount, such as GPT-5.4 cached input at 0.125.
- Reject unpriced admission for cost-limited keys with pricing_unavailable. If actual upstream usage becomes unpriced after admission, retain the admitted cost allowance and store actual cost as unknown; token/request limits settle normally and repeated settlement is idempotent.
- Use explicit source-pricing context and explicit zero rates for non-inference routes. Neither can accidentally fall back to a public model with the same name.
- Retain persisted historical amounts and pricing versions without recalculation.

## Risks / Trade-offs

- Narrower aliases can turn a previously guessed price into an unknown price. Regression tests cover supported models and snapshots as well as unknown variants.
- The existing bounded admission budget cannot predict the full upstream conversation context. Unknown final context prices retain the already reserved allowance rather than pretending to be free.
- The official table and Daybreak targets can change. Record a verification date and update reviewed code and expectations together.

## Rollout

The database schema is unchanged. Validate the exact package, retain the previous executable artifact, drain traffic and verify the new process before completing activation. A code rollback preserves new business data and does not downgrade the existing timing schema.
