## Why

From 2026-10-13 20:04 through 2026-10-14 20:35 (Taipei), about 560 Responses streams failed with upstream SSE `code=internal_error` and message `response protection is unavailable`. codex-lb returned HTTP 502. All of them used one Codex Desktop key and `gpt-5.6-sol`. At least the first was an `input_image` request, which bypasses the HTTP bridge and is posted upstream as HTTP SSE. The same path succeeded for other image requests at the same time, so the upstream failure is intermittent. `internal_error` was not in the pre-output retry set, the raw upstream error was not stored on `request_logs`, and the inbound request id printed on the bypass log could not be found for the successful rows. About 33 HTTP 400 responses per hour with `There was an error parsing the body` were also missing from `request_logs`.

## What Changes

- Before any output is forwarded, an upstream SSE `internal_error` whose message is `response protection is unavailable` uses the existing same-account transient retries and then at most one account switch. That switch shares the one-resend budget with admission failover and cached-history replay. An anchored HTTP SSE turn drops `previous_response_id` and resends cached history, or stays on the original account when the cache misses. After output has started, the error is forwarded once and the account does not change.
- Every upstream SSE stream error writes `upstream_error_code`, `failure_phase`, and `failure_detail` (message, type, and param) and emits one log line without credentials or request content.
- Request-log search matches `archive_request_id`, so the id printed when an image request bypasses the bridge finds the success row.
- OpenAI-format HTTP 400 responses with `There was an error parsing the body` are written to `request_logs`.

## Capabilities

### Modified Capabilities

- `responses-api-compat`: pre-output retry for this upstream `internal_error` message, capped at one shared account switch.
- `conversation-history-replay`: an anchored response-protection failure resends cached history or stays on the owner.
- `proxy-runtime-observability`: stream-error request-log fields, one log line, archive-id search, and body-parse request logs.

## Impact

HTTP Responses streaming (`app/modules/proxy/_service/streaming/mixin.py`), request-log search (`app/modules/request_logs/repository.py`), and the OpenAI HTTP exception handler (`app/core/handlers/exceptions.py`). No new setting, no schema change, no dashboard navigation change. Release versions move to 1.24.9 with `Chart.yaml`.
