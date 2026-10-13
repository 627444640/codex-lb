## 1. Implementation

- [x] 1.1 On the HTTP bridge, before the `previous_response_not_found` fail-closed rewrite, resend once from cached history when the shared anchor-loss candidate matches.
- [x] 1.2 Record `history_replay_reason=previous_response_not_found` on the request state the request log already reads. Do not log `continuity_fail_closed` for a resend that is sent.
- [x] 1.3 Report `fresh_replay_available=true` on the HTTP path when the cache holds a replayable chain. Leave direct WebSocket diagnostics unchanged.
- [x] 1.4 Keep the resend on the owning account for a hard session. Do not reassign an unavailable sticky owner.
- [x] 1.5 A cache miss, model output already forwarded, or a failed send returns the original terminal and does not send a second time.

## 2. Tests

- [x] 2.1 `previous_response_not_found` with a cached chain resends once and does not emit the fail-closed terminal.
- [x] 2.2 `previous_response_not_found` with no cached chain returns the original `stream_incomplete` terminal and `fresh_replay_available=false`.
- [x] 2.3 Model output already forwarded: no resend, and `fresh_replay_available=true` when the cache holds the chain.

## 3. Release

- [x] 3.1 Bump the package version to 1.24.7.
