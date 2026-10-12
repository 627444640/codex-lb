## 1. Implementation

- [x] 1.1 Classify accepted pre-output `server_error` and overload as one admission retry.
- [x] 1.2 Replay cached history without `previous_response_id` and close the original upstream first.
- [x] 1.3 Surface a client-anchor cache miss and any turn that already emitted model output.
- [x] 1.4 Record `admission_failover_retried` and the source account on the request log.
- [x] 1.5 Apply the same rule on the HTTP bridge and HTTP streaming paths.

## 2. Regression coverage

- [x] 2.1 Accepted `server_error` / overload before output fails over once and is logged.
- [x] 2.2 Output already delivered does not fail over.
- [x] 2.3 History failover plus a second failure surfaces.
- [x] 2.4 The resend omits `previous_response_id`.
- [x] 2.5 A cache miss surfaces with no failover.
- [x] 2.6 Tool-call-only and reasoning-only output block failover.
- [x] 2.7 The original upstream is closed before the switch.
