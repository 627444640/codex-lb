# Published token price estimates

## Purpose and sources

The [requirements](spec.md) describe how model rates, service tiers and upstream token partitions affect cost limits. Rates were checked against [OpenAI API pricing](https://developers.openai.com/api/docs/pricing) on 2026-09-17. These amounts estimate API retail value; they are not subscription charges. Custom model sources retain their own configured prices.

## Rationale and boundaries

Use exact model entries and numeric dated snapshots because a family prefix does not imply the same price. For example, 100,000 ordinary input plus 1,000 output tokens on GPT-5 Mini costs $0.027, while using GPT-5's price would produce $0.135. Daybreak blue/red currently resolve to Sol/GPT-5.6 Cyber and need rechecking in future price updates.

Cache writes and cached reads are disjoint subsets of input. A cache write replaces an ordinary input token at its write rate; it is not an additional charge on top of the ordinary input rate. Requests over 272,000 input tokens use the model's published long-context rates for the whole request.

## Missing prices and evidence

Unknown variants, Ultrafast, unsupported tiers and unpublished long-context combinations do not inherit Standard rates. Their request-log estimate stays unknown. Missing image modality details and unreported cache writes are separate evidence limitations. Persisted historical amounts are not repriced on reads.

Cost-limited requests cannot treat an unknown estimate as free: admission rejects unpriced requests, and an upstream switch to an unpriced result retains the already admitted allowance without claiming it is the actual cost. Explicitly known zero-cost results are different and release the allowance normally. Token and request counters still settle from reported usage.

The official GPT-5.4 Flex table rounds cached input to $0.13; exact 50%-of-Standard arithmetic remains $0.125. GPT-5.6 Cyber has no published long-context table and a documented 272,000-token input limit; no long-context rate is inferred. Deprecated models retained for historical compatibility do not imply current API availability.

## Operations

Rate changes are reviewed code changes with a source date, boundary tests, API-path regression tests and pricing provenance. No network fetch is added to the request path. Keep deployed application versions separate from source checkouts and preserve the installed package for rollback before deployment.
