The user-facing limit in this change is the serialized outbound
`response.create` budget, not the downstream Uvicorn message limit. The latter
already defaults to 128 MiB so a large client message can reach the application
guard. The upstream frame constant is set one MiB higher (65 MiB) so the
64 MiB serialized request remains below the frame ceiling after the envelope
and transport metadata are accounted for.

The limit remains a fixed application constant. The legacy
`CODEX_LB_MAX_SSE_EVENT_BYTES` and
`CODEX_LB_UPSTREAM_RESPONSE_CREATE_MAX_BYTES` names stay inert and continue to
produce their existing removed-setting warning; this change does not reopen
those operator knobs. Automatic transport selection still reserves its
existing two MiB frame headroom and therefore uses its corresponding derived
threshold.

The safety boundary is intentionally layered: a request over 64 MiB is first
slimmed in the historical portion where possible, then rejected locally with
the existing `400 payload_too_large` envelope if it remains too large. A
request between the old 15 MiB limit and the new 64 MiB limit can now be sent
through the upstream WebSocket path without changing routing, retry, or
settlement semantics.
