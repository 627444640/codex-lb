## Why

The upstream WebSocket path is currently selected for Responses payloads until
the local 63 MiB frame-budget estimate is exceeded. The live upstream has
closed a 38.9 MB `response.create` with WebSocket close code `1009`, so that
local frame budget is larger than the upstream path can safely accept. Large
conversation payloads commonly contain inline images and tool output, and
replaying the same oversized body only repeats the close.

## What Changes

- Add a fixed 30 MiB automatic WebSocket safety budget for Responses payloads.
- In automatic transport selection, route payloads above that budget through
  upstream HTTP/SSE before opening a WebSocket.
- Apply the same budget to the image-aware HTTP fallback predicate so image
  payloads do not remain on WebSocket merely because they are below the local
  63 MiB frame budget.
- Preserve explicit `upstream_stream_transport = "websocket"` behavior; an
  operator pin remains an explicit compatibility choice.
- Add regression coverage and update the Responses transport OpenSpec.

## Impact

- Affected capability: `responses-api-compat`.
- Affected code: stream transport selection and image-aware fallback routing.
- Requests at or below 30 MiB keep the existing automatic model-preference
  decision. Larger automatic requests use HTTP/SSE and avoid the known
  upstream WebSocket 1009 path.
- This does not claim that 30 MiB is an official upstream limit; it is a
  conservative local safety budget based on observed upstream behavior.
