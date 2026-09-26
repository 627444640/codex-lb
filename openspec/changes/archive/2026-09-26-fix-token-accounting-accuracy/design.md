## Context

See proposal.md. The current maintenance baseline already contains these defects. The internal candidate removes prices but intentionally retains success-only quota settlement. Historical hourly rows already store both output_tokens and output_or_reasoning_tokens; no schema change is needed to make dashboard aggregation consistent with the existing report/log lower-bound rule.

## Goals / Non-Goals

Goals: protect counters from malformed upstream numbers; carry Responses terminal state through bounded/unbounded forwarding; consistently expose known totals and partial evidence; merge verified source changes into the requested local release branch.

Non-goals: changing successful-request quota into all-consumption billing, reconstructing historical missing usage, audio accounting redesign, retention redesign, changing account routing, deployment, or pushing GitHub branches without an explicit request.

## Decisions

1. Validate non-negative integer counters at parsing and settlement boundaries. Reject invalid evidence rather than clamping negative consumption to zero. Preserve negative reservation deltas used for legitimate refunds; a direct service call must not bypass validation. Parsing must fail safely without exposing upstream request bodies or credentials.
2. Track a typed terminal outcome alongside model-source streaming usage. HTTP 200 and transport EOF do not establish a successful Responses result. Preserve failed/incomplete usage for logs, release reservations using existing unsuccessful-request policy, and preserve downstream failure events. Apply the same failure handling to explicit failed/incomplete non-streaming Responses results; preserve existing status-absent JSON compatibility. Keep Chat Completions behavior intact. Missing terminal, disconnect and exception cleanup must remain owned and idempotent.
3. Keep existing known-token lower-bound semantics (input + output-or-reasoning) and reuse the hourly output_or_reasoning field for dashboard reads. Removing the fallback globally would discard known historical reasoning and change established API/account behavior. Derive complete/partial/missing status from raw nullable fields rather than storing a second source of truth. Preserve output null when unknown; explicitly label any known total or lower-bound display. Aggregate descriptions explain that unknown usage is excluded; no per-hour completeness column or migration is added.
4. Preserve live service and data. Use the existing guarded test runner, temporary SQLite and fake upstreams. No production credentials or real generation requests are needed. Checkpoint the pre-existing internal implementation separately so the three fixes are reviewable relative to it.

## Risks / Trade-offs

- Stricter validation may expose previously tolerated malformed providers: keep invalid evidence distinct from measured zero and test cleanup and external route behavior.
- Failed streams can legitimately consume tokens: retain usage in logs, but maintain current documented success-only limits; do not silently redesign quota policy.
- Known totals are a lower bound for partial/unknown records: label them accordingly instead of presenting inferred output as measured complete usage.
- Historical reports still have pre-existing retention/window differences: scope parity tests to identical retained request sets and document that boundary.

## Migration Plan

No database migration, data backfill or dependency upgrade. Run isolated regressions and static/spec checks, review the final patch, commit on the dedicated branch and merge locally into v1.24.1. Deployment is a separate step requiring a fresh build from the selected commit and a controlled rollout.
