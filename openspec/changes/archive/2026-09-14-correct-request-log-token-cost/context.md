# Request token and cost correction

Owner specifications: [observability](../../../specs/proxy-runtime-observability/spec.md),
[image compatibility](../../../specs/images-api-compat/spec.md), and [API keys](../../../specs/api-keys/spec.md).

This change separates reported token evidence from retail API cost estimates.
Input includes cache reads and cache writes; output includes reasoning. They
are subsets, not additional tokens. Request model remains the routing/display
identity, while actual response model determines builtin pricing when reported.

The pricing snapshot is `openai-api-2026-09-14-v1`, verified against the
[official pricing table](https://developers.openai.com/api/docs/pricing) and
[cache usage documentation](https://developers.openai.com/api/docs/guides/prompt-caching#monitor-cache-performance).
Sol's published promotional rates apply through at least 2026-11-21; future
changes require another reviewed pricing version. No public price is assigned
to `codex-auto-review`. These figures are API estimates, not subscription credit
charges or a provider invoice.

For example, Luna with 16,280 input, 15,104 cached reads, 100 cache writes and
63 output tokens costs $0.00061788 at the standard short-context rates. Its total
tokens are 16,343. The request table displays $0.000618 instead of $0.00 and its
details identify the input subsets. The JSON API retains the unrounded amount.

Historical rows keep their stored cost. A previously unpriced row may display
a current estimate when enough evidence exists, with missing-write warnings;
this read does not backfill storage or folded aggregates. Aggregate captions
identify the known portion. Without original upstream usage, historical cache
writes and image modality cannot be reconstructed reliably.

Image public usage replaces the host response model, counts and cost atomically
under the existing fold-state lock. A current image cost explicitly marked unknown
stays unknown on subsequent reads. Custom source estimates retain their source
pricing provenance and are not reconstructed from builtin rates. Success-only
quota settlement and unknown-cost quota behavior remain unchanged; admission
reserves a conservative price bound independently of final accounting.

Validation uses synthetic traffic and temporary SQLite/PostgreSQL databases.
No real account credentials, request payload archives or local deployment files
are part of this change. Browser comparison images use example.com fixture
accounts only.

Browser comparison: [before](evidence/request-cost-before.png) and
[after](evidence/request-cost-after.png), using identical synthetic request
payloads. Both rendered without browser page errors. The real API browser
smoke test also passed using an empty temporary database.
