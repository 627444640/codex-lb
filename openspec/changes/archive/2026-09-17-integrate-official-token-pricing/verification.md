# Verification: current-main official token pricing integration

Baseline: `d1fd2f21fa0e0f3b5fcad3af5fada19693cd1fc1`. This is a focused integration of pricing and required accounting evidence; unrelated release-branch authentication, macOS and metrics ancestors are not included.

## Local evidence

| Area | Result |
|---|---|
| Backend accounting, quota, source/image, HTTP/WebSocket, logs/backfill and migration | 2,470 passed |
| Pricing/catalog/scheduler final unit and mock HTTP integration | 208 + 3 passed |
| Backend/catalog coupling after independent-review fixes | 220 passed |
| Frontend cost/schema/formatting suites | 197 passed |
| Synthetic current-main before and after browser checks | 1 passed each |
| Full `make lint` | Passed: architecture, cancellation safety, timing seams, settings tiers, migration topology, Ruff and formatting |
| Full `ty check` | Passed |
| OpenSpec strict main-spec validation | 65 of 65 passed |
| Migration topology | 261 revisions, one head; new nullable metadata revision extends actual main's OIDC head |

Counts are separate runs and are not summed as unique tests. Tests use isolated databases, fake upstreams and synthetic browser fixtures. No production service was changed during main integration.

## Independent review

Two reproducible catalog integration findings were fixed and independently rechecked:

1. Partial catalog records no longer discard known context thresholds and service-tier prices. Compatible partial records retain complete evidence and version; conflicting partial records retain last-good; complete new records can still update prices, including equivalent multiplier/explicit Priority representations.
2. Versioned NULL costs remain unknown between a catalog refresh and atomic backfill. The API does not combine a newly calculated amount with an older price version. Complete text evidence still becomes repairable when a model or tier gains a price.

Other reviewed invariants include one captured price for amount and fingerprint, historical non-NULL preservation, independently configured source prices, unknown-cost reservation retention, explicit zero and numeric-field validation.

## UI evidence

`evidence/pricing-table-before.png` is rendered from the current-main baseline. The after table, cost detail and unknown-price detail use the same synthetic fixtures. The browser setup intercepts or rejects all backend and external requests. The fixtures contain no production account, token, client address or session data.

## Merge boundary

Local verification does not satisfy the GitHub merge gates. The current PR head still requires successful cloud checks, resolved actionable CodeRabbit findings and a clean merge state. No CI configuration or check was disabled to obtain local results.
