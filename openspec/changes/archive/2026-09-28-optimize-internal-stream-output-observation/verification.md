# Verification — 2026-09-28

Feature branch: `feat`, based on internal `v1.24.2` at
`79ae33af840526e833fbc797eb19e08edbca0b63`.

## Completeness, correctness and coherence

The single new requirement and all three scenarios are implemented. The common
canonical flat-object subset avoids JSON-object decoding. Unsupported, ambiguous,
oversized and unusual numeric payloads retain the existing parser, including its
large-integer failure behavior. Both observations share the same state update.
No required scenario is unimplemented and the scoped design review found no
remaining correctness mismatch.

Production changes are limited to `response_timing.py`, the HTTP/SSE branch of
`streaming/mixin.py`, and the matching support export. There is no schema, metric
policy, dependency, setting, UI, release-version or deployed-runtime change.

## Regression evidence

- Final related proxy/bridge/WebSocket/timing/request-log selection: **2,279 passed**.
- Focused differential/timing suite: **176 passed**, including a 300-example
  generated-JSON parity test. This subset is included in the larger selection.
- The actual streaming entrypoint retains exactly three full parser calls for
  one or 256 supported post-TTFT output frames, with no fallback parser calls.
- Actual reasoning-first streams preserve TTFT, first-output time, raw frames and
  nonempty counts for empty, duplicate-key, escaped-key, nested, non-string and
  malformed frames. Empty output never makes a one-chunk sample eligible.
- Tests cover five output event types, three content fields, Unicode/escaped/control
  content, decoder fallback, frames beyond 64 KiB and the interpreter's integer guard.
- Full Ruff lint, changed-file formatting, changed-file type checks and proxy
  architecture checks passed. The change and owning capability pass strict
  OpenSpec 1.11.0 validation.

## Synthetic observation benchmark

Command: `.venv/bin/python -m scripts.benchmark_stream_output_observation`.
CPython 3.13.15, Darwin arm64, 10,000 observations per batch, seven repeats,
alternating measurement order and reporting medians. Both paths assert identical
state. The baseline is the complete JSON decoder plus parsed observation.

| Case | Decoded path (microseconds) | Fast/fallback path (microseconds) | Time change |
| --- | ---: | ---: | ---: |
| short_text | 2.7392 | 1.5751 | -42.50% |
| empty_text | 2.6310 | 1.1257 | -57.21% |
| unicode_text | 2.9968 | 1.3274 | -55.71% |
| escaped_text | 2.6685 | 1.3157 | -50.69% |
| tool_arguments | 2.7039 | 1.3418 | -50.37% |
| large_1k_text | 6.7071 | 4.4866 | -33.11% |
| large_16k_text | 70.5186 | 53.7964 | -23.71% |
| fallback_nested_metadata | 2.6990 | 4.0846 | +51.34% |
| fallback_nonstring_delta | 2.5994 | 3.8471 | +48.00% |

Supported short/Unicode/tool samples reduce observation work by roughly 42–56%;
the 16 KiB sample reduces it by roughly 24%. Unsupported nested/non-string samples
cost an additional roughly 1.2–1.4 microseconds because they attempt classification
before decoding. This is an explicitly reported trade-off, not an all-frame speed
claim. These results measure the observation operation only, not production CPU,
request throughput, TTFT or model generation speed. Raw results are in
`evidence/benchmark.json`; benchmark timing is not a machine-dependent test gate.

## Existing baseline limitations

The following files are byte-identical to `v1.24.2` and were not changed here:

- Full formatting reports three pre-existing files: `deploy/macos/tests/integration_auth_policy.py`,
  `deploy/macos/tests/test_core.py`, and `deploy/macos/tests/test_manage.py`.
- Full typing reports eight pre-existing diagnostics in
  `tests/integration/test_managed_auth_policy.py` (nullable row handling).
- Before spec synchronization, all main-spec files were unchanged from v1.24.2.
  Full strict OpenSpec reports 36 passing and 22 failing capabilities; the owning
  `proxy-runtime-observability` capability passes. The failures report placeholder
  Purpose sections. This is not a claim that repository-wide static gates are green.

These baseline checks should be reconciled before declaring v1.24.3 release-ready.
The upstream-only cancellation/timing-seam checker scripts are not present in this
internal baseline; their absence is not reported as a passing check.

## Later v1.24.3 integration

The user requested this feature and the independent status-page work to be combined
later in v1.24.3. The feature and current status-page working changes have no file
intersection. This is a scope check, not combined-runtime acceptance.

Keep the two changes as separate commits when preparing v1.24.3, then run combined
proxy/timing and Settings/auth/guest-boundary tests plus the status-page browser
checks. The status-page work stays in the original working directory. This task
does not create/merge v1.24.3, publish a release, deploy or restart the service.
