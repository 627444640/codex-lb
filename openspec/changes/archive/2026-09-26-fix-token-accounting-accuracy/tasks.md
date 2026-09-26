## 1. Usage validation

- [x] 1.1 Validate non-negative upstream counters and guard direct quota settlement; verify malformed/negative inputs cannot refund prior usage and valid zero remains valid.
- [x] 1.2 Add route/service regression coverage for negative evidence, valid reservation refunds and repeated settlement; run isolated affected tests.

## 2. Responses terminal outcomes

- [x] 2.1 Propagate model-source terminal state through stream/log/settlement paths; verify failed/incomplete/unterminated streams are not successful while known usage remains logged.
- [x] 2.2 Test limited/unlimited source Responses routes, completed streams, cleanup and existing chat compatibility using fake upstreams.

## 3. Consistent known-token presentation

- [x] 3.1 Align dashboard cards and trends with log/report known-token totals; verify partial and complete examples before/after hourly folding without data rewrites.
- [x] 3.2 Expose complete/partial/missing request usage, preserve unknown output and explain aggregate known totals in UI; verify API and frontend behavior.

## 4. Integration and delivery

- [x] 4.1 Sync owning specification/context and user documentation, then run strict change/spec validation.
- [x] 4.2 Run affected integration/unit/frontend checks, lint/type/architecture checks, and independent final-diff review; record exact results and limitations.
- [x] 4.3 Prepare the verified source delivery record, including the separate internal checkpoint and unchanged installed-runtime hashes; confirm no migration or dependency change.

After verification, archive this change and commit on the dedicated branch, then merge locally into v1.24.1 as requested. Record the actual merge identity in the local delivery report.
