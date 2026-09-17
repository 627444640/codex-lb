# Current-main pricing integration

## Scope and sources

This change integrates the verified pricing behavior from the earlier release branch into main's automatic metadata catalog and current request lifecycle. Source behavior is recorded in public commit 9e932343; unrelated authentication, platform tooling and metrics ancestors are excluded.

The official price evidence was fetched on 2026-09-17 from https://developers.openai.com/api/docs/pricing and the model/prompt-caching documentation. These amounts are retail API estimates, not subscription charges. Model-source prices remain independently configured.

## Catalog decisions

The active catalog still takes precedence over offline snapshots and code defaults. Explicit Priority/Flex long-context fields remain authoritative. Pricing versions identify the effective model-rate content, so a changed catalog cannot make a previously saved amount appear calculated with a newer price. Updating an unrelated model does not change another model's version.

Snapshots carry new optional numeric cache-write/modality fields and retain compatibility with earlier snapshots. Compatible partial records can inherit verified supplementary fields. If base rates conflict and new data omits formerly known write/modality prices, retain the last complete model record until consistent metadata is available; never attach old extra rates to incompatible new base prices.

The known unpublished identifiers gpt-5.3, gpt-5.3-codex-spark and codex-auto-review remain excluded across remote parsing, stored-cache decoding and bundle loading as of this verification date. This does not disable unrelated explicit catalog entries. Revisit this exclusion when a verified public price becomes available.

## Accounting boundaries

Input, cached reads and writes are disjoint partitions. Image totals require their modality evidence. A known model on an unsupported tier/context remains an unknown estimate; for cost-limited keys, unavailable requested prices are rejected before forwarding. If actual upstream pricing becomes unknown after admission, retain the admitted allowance without claiming it is an actual known charge. Known zero remains distinct.

Historical non-NULL amounts are preserved. Existing automatic NULL-cost repair still works when a later catalog recognizes a model and complete evidence exists. It skips model sources and image rows whose required modality information was not persisted; pricing-version presence alone does not disqualify a repairable text row.

For example, 100,000 ordinary input and 1,000 output tokens on the verified Mini Standard entry cost $0.027 rather than the old generic-family $0.135. The same actual tokens on an unpriced tier do not become a zero-cost quota settlement.

## Validation and publication

Synthetic UI fixtures provide before/after evidence from the same main baseline. Migration tests extend the actual main head and preserve previous costs and usage. Merge is separately gated by the actual GitHub head's CI, review threads and clean merge state; local tests do not replace those gates.
