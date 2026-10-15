## 1. Pre-output retry

- [x] 1.1 Before any client output, treat upstream SSE `internal_error` with message `response protection is unavailable` as a transient failure and reuse the existing same-account retry and account switch.
- [x] 1.2 After model output or any forwarded event, keep the error terminal: one copy to the client, no account switch.

## 2. Request logs

- [x] 2.1 Store upstream SSE error code, message, type, and param on `upstream_error_code`, `failure_detail`, and `failure_phase`, and emit one log line without credentials or request content.
- [x] 2.2 Match `archive_request_id` in request-log search so an image-bypass success is findable by the id printed on the bypass line.
- [x] 2.3 Write OpenAI-format HTTP 400 `There was an error parsing the body` rows, with the cause type and without the body.

## 3. Verification

- [x] 3.1 Unit tests cover pre-output retry, post-output refusal, unrelated `internal_error`, request-log fields, image-bypass archive lookup, and the body-parse 400.
- [x] 3.2 `uv run ruff check` on the changed Python files passes. `uv run ty check` reports no diagnostics in the changed files. The full-project check still reports two existing diagnostics in `tests/unit/test_http_bridge_anchor_loss_history_replay.py`.
- [x] 3.3 Bump every release-managed version field to 1.24.9, including Chart.yaml version and appVersion.

## 4. Shared switch budget

- [ ] 4.1 A response-protection account switch consumes the same one-resend budget as admission failover and cached-history replay. The second account's failure is returned, and a request that already switched does not switch again.
- [ ] 4.2 An image HTTP SSE request with `previous_response_id` drops that id and resends cached history when it switches. A cache miss retries only the original account.
