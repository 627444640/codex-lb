# Response protection unavailable

## Purpose

Hide one intermittent upstream SSE failure when the client has not yet seen output, and make the failure and the two missing request-log cases visible to operators.

## What production showed

The upstream event was `code=internal_error`, `message=response protection is unavailable`. That string is not produced by this repository. Image input (`input_image=True`) disables the HTTP bridge in `_stream_http_bridge_or_retry` and posts the request as HTTP SSE through `_stream_with_retry`. `internal_error` was not in `_TRANSIENT_RETRY_CODES` or `ADMISSION_FAILURE_CODES`, so the mixin yielded the error and raised `_TerminalStreamError`. The client saw HTTP 502 because unknown error codes use that status. Some image requests on the same path succeeded, which is why a pre-output retry can help.

## Retry decision

The existing transient loop retries the same account up to three times, then excludes it and selects another account, up to three accounts, and only while nothing has been sent downstream. This change raises `_TransientStreamError` for this one message before the error or any held `response.created` / `response.in_progress` prelude is forwarded. `preserve_on_selection_exhausted` keeps the upstream code and message when no account remains. `allow_transient_retry` is the budget flag the loop already passes in.

The match is the whole message after whitespace collapse and casefold. A longer sentence, or any other `internal_error`, stays terminal. Adding `internal_error` to the global admission set would trip the admission breaker and one-shot failover for unrelated internal errors.

After a model-output event has been seen, or any event has been forwarded, the error is yielded once. The account is not switched and the output is not repeated.

Held prelude is not client output. A `response.created` that is still buffered does not block the retry, and it is not flushed when the attempt is abandoned.

## Why success rows looked missing

`_stream_once` always writes a request log. On success, `request_id` becomes the upstream response id and `archive_request_id` keeps the inbound id that the bypass log prints (`ensure_request_id()`). Errors that arrive before `response.created` keep that inbound id in `request_id`, which is why the 560 failures were findable and the successes were not. Search compared `request_id` only. The row is not rewritten; search now also matches `archive_request_id`.

## Why the 400s were missing

FastAPI 0.136 reads the body before route dependencies. `JSONDecodeError` becomes a validation error. Any other exception, including `ClientDisconnect`, becomes `HTTPException(400, detail="There was an error parsing the body")`. That happens before the API key and before any proxy request log. The OpenAI exception handler logged the response and did not insert a row.

The handler now inserts one row for that exact detail on OpenAI-format paths (`/v1/` and `/backend-api/`, or `error_format=openai`). `failure_phase` is `validation`, `failure_detail` is the cause type, `upstream_status_code` is null, and `api_key_id` is null because the key dependency has not run. The body is not stored.

## Example

Upstream, before any output:

```text
event: error
data: {"type":"error","error":{"code":"internal_error","type":"server_error","param":null,"message":"response protection is unavailable"}}
```

The proxy retries the same POST on the same account, then another account if those retries fail. The client sees only the later success, or one copy of this error if the budget is exhausted. The failed attempt's request log stores `upstream_error_code=internal_error`, `failure_phase=upstream`, and `failure_detail` containing the message, `type=server_error`, and `param` when present. The console line is `upstream stream error` with those fields.

## Failure modes

- Output already forwarded: no retry, no second account, the error event is sent once.
- Message is only a prefix or a different `internal_error`: no retry.
- Every account fails before output: the client receives `internal_error` and the upstream message, not a generic `no_accounts` event.
- Body-parse logging fails: the HTTP 400 is still returned; the write failure is one warning.
