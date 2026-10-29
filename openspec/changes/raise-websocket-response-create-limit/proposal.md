## Why

The fixed upstream Responses WebSocket request guard rejects serialized
`response.create` payloads above 15 MiB. Conversation history with inline
images and tool output can exceed that amount before the request reaches the
upstream service, even when the client-facing Responses ingress budget still
has room. The effective request budget should be large enough for these
payloads while retaining a bounded frame ceiling and the existing local
fail-fast behavior.

## What Changes

- Raise the effective serialized upstream `response.create` budget to 64 MiB.
- Raise the shared upstream SSE/WebSocket frame budget to 65 MiB so the
  serialized request keeps its existing one MiB envelope headroom.
- Keep the 128 MiB client-to-proxy Responses ingress budget unchanged; it is a
  separate transport limit.
- Update the Responses, deployment, and SSE framing OpenSpecs and add a
  regression assertion for the derived constants.

## Impact

- Affected capability: `responses-api-compat`.
- Affected deployment documentation: `deployment-installation`.
- Affected code: `app/core/clients/proxy.py` and comments describing the
  response upload/file bypass boundary.
- Existing historical slimming and local `400 payload_too_large` behavior is
  unchanged for payloads that still exceed 64 MiB after slimming.

## Non-goals

- This does not change `--ws-max-size` or `UVICORN_WS_MAX_SIZE`, whose default
  remains the independent 128 MiB downstream ingress budget.
- This does not change HTTP request-body limits or upstream file-upload limits.
