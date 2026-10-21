## Context

Tracking: https://github.com/627444640/codex-lb/issues/16 (parent #15).

The precreated-retry predicate currently returns a boolean for both a future cooldown and an occupied half-open probe. Some consumers then read a cooldown again and force a minimum one-second delay, even if the observed cooldown is zero. This conflates local refusal with an upstream timeout. The existing durable recovery path already has operation fencing, source-generation claims, physical-send deduplication and sibling dispatch-state classification; those mechanisms are not missing features.

## Goals / Non-Goals

**Goals:** establish characterization coverage, retain replay safety, and surface truthful gate outcomes at the real HTTP/SSE boundary. Keep the change small enough for an independent review.

**Non-goals:** remove the circuit, change its qualifying failures or timeouts, disable the account breaker, widen ownership, add blanket continuity exemptions, clear old durable rows, introduce endpoint quarantine or TTFT-based routing, change generic-backoff selection, or deploy production.

## Decisions

1. Keep one authoritative gate evaluation. Use a typed result carrying allowed/denied, a bounded reason and an optional genuine retry duration. The legacy boolean helper must remain a boolean adapter, never a truthy result object. Do not evaluate or reserve the half-open probe twice.
2. Preserve the current allowance asymmetry: fresh-hard-account-switch and proof-gated continuity flags can follow their existing half-open behavior; operation-fenced continuity only follows its existing future-cooldown allowance and must not bypass a busy half-open probe.
3. A future local or restored durable deadline maps to `bridge_session_cooldown`. Half-open occupancy and generation conflict do not manufacture a deadline. Persistence failures retain the existing recovery-persistence fail-closed contract. Exact claim outcomes must distinguish CAS rejection from unavailable infrastructure; they must not authorize a send.
4. Keep the original deadline, operation identity, source generation, replay count, sequence/output guards and reservation settlement order. Same-owner recovery and account-neutral recovery retain their distinct authorization paths. The new gate code is not an ambiguous-upstream-transport signal.
5. Update all affected consumers deliberately: startup collection, already-started SSE, owner forwarding, retry/recovery code allowlists, request logs and tests. Before response commitment, use the HTTP envelope and integer-second Retry-After. After commitment, emit one terminal event and only the existing real millisecond retry hint.
6. Keep old durable failure counts/deadlines/generations intact across restart and rollback. No migration, row purge or constant reduction is part of this change.
7. Failure attribution is physical-attempt scoped. Explicit PRNF or local cleanup for one request cannot relabel sibling evidence. Sent eventless siblings remain UNKNOWN; siblings with response events remain ACKNOWLEDGED. An existing correct path receives regression coverage rather than an unnecessary rewrite.
8. Use only synthetic fixtures and sanitized summaries. Raw local test output remains ignored; review text must not contain production identifiers, credentials or payloads.

## Risks / Trade-offs

- Changing an error code can alter startup retry allowlists. Tests must prove no new hidden dispatch and no loss of existing owner-fenced behavior.
- A second read can race the original gate. Derive the result from the authoritative decision snapshot rather than inferring a precise old reason from a later empty state.
- Returning a dataclass from a legacy boolean method would silently admit refusals. Keep a real boolean wrapper and test exact `is True`/`is False` behavior.
- A broad cleanup exemption could suppress a sibling's real failure. Preserve attempt identity and existing pre-response eligibility.
- Existing main specifications and active deltas must both be consulted; this change does not archive unverified historical work.

## Rollout and rollback

Build characterization tests first. Publish the gate contract and implementation as a focused PR only after strict OpenSpec validation and relevant unit/route regressions pass. Leave existing release PR #1 untouched. Rollback restores the previous wheel while keeping durable tables and historical request logs intact. No production rollout is included in this change's local implementation scope.
