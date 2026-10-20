# Clear stale durable anchors before bounded history recovery

## Why

An HTTP bridge can identify an upstream `previous_response_not_found` while a
proxy-managed durable anchor is still present in the live session. If the
history replay is refused by its token/byte budget or the replacement send
fails, the next client retry can receive the same expired anchor and repeat the
failure indefinitely.

## What changes

- In fail-closed HTTP bridge handling, classify `previous_response_not_found`
  before rewriting it to `stream_incomplete`.
- Fenced-clear the matching durable anchor and the live process-local anchor
  as soon as a proxy-injected `previous_response_not_found` is classified,
  before checking whether the request qualifies for cached history replay.
- Never clear a client-supplied `previous_response_id`; the proxy has no
  ownership evidence for that anchor.
- Preserve the 128,000-token and 15 MiB replay limits; an over-budget replay
  remains fail-closed and never truncates input.
- Keep history replay, account switching, and transport retry on one shared
  `replay_count` budget, and refuse all retry after model output is visible.
- If durable cleanup fails, clear the local anchor, record the failure, and
  fail closed or continue without the invalidated anchor rather than rebinding
  the same `previous_response_id`.

## Trade-off

After an expired proxy-managed anchor is cleared, a client that does not send a
complete history on its next request may be treated as a new unanchored turn and
can lose prior conversational context. That bounded loss is preferable to
re-injecting the same expired anchor and keeping the client in an infinite
`previous_response_not_found` loop.

## Scope

The change is limited to the HTTP bridge recovery path and its unit/regression
tests. It does not alter deployment or account data schemas.
