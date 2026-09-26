# Token accounting accuracy verification — 2026-09-26

## Scope and identity

Work is isolated on `fix/token-accounting-1.24.1-20260926`, branched from local `v1.24.1` at `a5836f109dac20efed9231653ab72fc5ce1abff6`. The previously reviewed internal implementation was checkpointed separately as `78632de00dff11d50a88c0bc1706fd40d1f5a791` after verifying that the entire working tree matched its saved patch. This fix is reviewed relative to that checkpoint.

This is a source-only local integration. No production migration, data rewrite, credential access, service restart, installation, GitHub push or PR merge is part of this change. Deployment artifacts must be rebuilt from the selected fixed commit.

## Requirement mapping

| Requirement | Implementation and observable regression |
| --- | --- |
| Invalid usage cannot reduce prior consumption | `app/core/usage/validation.py`, `app/core/openai/models.py`, `app/modules/api_keys/service.py`; `test_usage_count_validation.py` and `test_api_key_usage_validation.py` verify invalid evidence remains unknown, counter 100/reservation 30 cannot become 95, release restores 100, valid 15-token settlement gives 115, zero and repeated settlement remain valid |
| Responses terminal controls outcome | `app/modules/model_sources/forwarding.py`, `app/modules/proxy/api.py`; `test_source_responses_terminal.py` and `test_source_responses_terminal_accounting.py` cover limited/unlimited SSE and JSON, completed/failed/incomplete, missing terminal, malformed usage, fragmented frames, disconnect, duplicate cancellation and safe persisted errors |
| Consistent known totals and partial evidence | `app/core/usage/logs.py`, request-log mapper/schema/repository and frontend; `test_request_usage_completeness.py`, `test_token_usage_consistency.py`, and `request-usage-presentation.test.tsx` cover complete/partial/missing/zero, raw output null and identical route totals before/after hourly folding |

The aggregate rule uses the existing `output_or_reasoning_tokens` hourly measure. No DB schema, migration, dependency manifest, raw history or timing/TPS calculation was changed.

## Executed checks

Backend executions use the existing `guarded_test.py`: a fresh temporary database/key, production data read/write denial, installed/service directory write denial, external-network denial and explicit production-port denial. Only synthetic upstreams are used.

| Check | Result |
| --- | --- |
| Negative usage, quota, existing service and log capture | 220 passed, 13.13s |
| Source terminal plus existing source forwarding/routing/API-key routes | 334 passed, 50.82s |
| Additional non-streaming terminal cancellation regression | 246 passed, 30.47s; focused terminal/forwarding/routing suite includes six additional JSON cancellation cases |
| New known-total completeness and API parity | 16 passed, 2.14s; eight combinations each checked before/after folding |
| Native Responses, WebSocket, Chat, compact and related unit contracts | 1,561 passed; one obsolete monetary-policy test subsequently updated and passed in the compatibility batch below |
| Existing log/report/rollup compatibility | 135 passed; four obsolete monetary-policy assertions subsequently updated and passed below |
| Updated report/hourly historical-data tests and legacy-cost WebSocket case | 63 passed, 10.70s |
| Frontend components, pages and schemas | 8 files / 138 tests passed, 7.68s |
| Frontend TypeScript, ESLint and production build | Passed |
| Actual browser with temporary backend and synthetic logs | Dashboard/report screenshots and API readback passed; partial is `≥ 120`, missing is Unknown, known total is 260, zero page errors |
| Ruff check/format, Ty, proxy architecture, diff check | Passed on the final source after the cancellation adjustment |
| OpenSpec | Change and owning specification strict validation passed; all 58 main specifications passed normal validation |

Batches overlap and must not be summed as a unique test count. The first negative-usage attempt needed a required `instructions` field in a new compact fixture; the frontend attempt needed a narrower test-field selector. Both were corrected and the complete corresponding batches passed. The browser harness initially expected heading “Reports” instead of the existing “Usage Report”; the corrected harness passed.

The five older compatibility failures were pre-existing internal-policy test drift, not changes needed in production code: report order now depends on requests, new writes ignore monetary overrides, usage updates preserve historical amounts, and dormant cost rules no longer block WebSocket requests. Their corrected tests retain actual historical amounts and verify them independently rather than weakening preservation checks.

## Independent review and browser evidence

An independent reviewer inspected terminal state, cancellation, SQL raw/fold partitioning, nullable API fields and frontend presentation. Review raised two actionable issues which were fixed: arbitrary terminal error text could enter logs, and a known terminal could be overwritten by a later cancellation. Persisted errors now use safe classifications, known outcomes retain precedence, and regression tests cover the cases. The independent review found no remaining actionable items in its reviewed patch. The root agent also reviewed the final focused JSON cancellation adjustment and its passing regression evidence.

Screenshots and local validation captures are excluded from published source. The before image is a frontend-only comparison: it uses the previous built frontend against the developing backend. It is not evidence for the old arithmetic defect; the September 26 audit and synthetic reproduction separately establish that defect. The after image uses the fresh built frontend and current backend. The blocked GitHub version-check attempt belongs to existing version discovery; external-network access remained denied.

## Limits and delivery

No real upstream model requests, PostgreSQL runtime suite, cloud CI, CodeRabbit review, Docker or Helm matrix was executed. Local verification is not presented as a GitHub PR merge gate result. Source validation and a separately built, verified deployment remain distinct acceptance steps.

Unknown historical usage remains unknown. Existing retention, time-window/account-filter differences and success-only quota policy remain; known consumption on failed requests may therefore differ from quota consumption. This change fixes the three audited mechanisms and does not claim a complete upstream-consumption ledger.

Private deployment records, local logs, screenshots and generated bundles are intentionally excluded from Git.
