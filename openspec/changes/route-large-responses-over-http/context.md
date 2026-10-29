The upstream close evidence is a serialized `response.create` of 38,855,272
bytes followed by close code `1009`. The existing automatic WebSocket decision
reserved only the local 65 MiB frame budget minus 2 MiB of transport headroom,
so the request was still routed over WebSocket. This change introduces a
separate, lower automatic fallback budget rather than changing the frame
ceiling or claiming a provider-published limit.

The 30 MiB value leaves room below the observed failure while keeping the
existing 64 MiB local response-create validation budget available for explicit
HTTP transport and for operators who knowingly pin WebSocket. The automatic
path is the safety boundary: it chooses HTTP before the upstream WebSocket is
opened. Explicit WebSocket remains available for compatibility and is tested
separately so this change does not silently override an operator pin.
