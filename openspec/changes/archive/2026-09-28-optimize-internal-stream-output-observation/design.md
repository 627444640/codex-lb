## Context

Base: internal v1.24.2 at 79ae33af840526e833fbc797eb19e08edbca0b63. The internal
`Output speed sample evidence is preserved` requirement counts nonempty content.
The upstream #2444 repair's event counter therefore cannot be transplanted as-is.

## Goals / Non-Goals

Reduce work on common canonical output frames with exact observation parity.
Do not change generation-speed policy or migrate to upstream's newer timing schema.
Status-page integration and v1.24.3 merging/deployment remain separate work.

## Decisions

- Match a complete, conservative flat object with one output string and a short
  allowlist of metadata keys. Full matching, rather than substring search, avoids
  counting nested keys or text that merely mentions an output field.
- Validate string escapes and JSON number syntax; recognize only JSON horizontal
  whitespace on the LF-only canonical path. Determine emptiness from the matched
  string span, without materializing decoded strings or object dictionaries.
- Bound fast observation to 64 KiB of characters and ordinary numeric lexemes;
  larger frames or unusual numbers retain the decoder, including its integer
  conversion limits. This bounds matcher work without adding a setting.
- Use possessive string repetitions to bound failure-time backtracking. Unknown
  structures fall back to `parse_sse_data_json`; this is a fast subset, not a new
  general JSON parser.
- Share the existing state update between parsed and fast observation so sample
  timestamps/counts remain identical, including reasoning-first and empty deltas.
- Use synthetic differential tests and the actual stream entrypoint. Benchmark
  representative short, escaped, tool, large and fallback frames separately; no
  machine-dependent timing threshold is a test gate.

## Risks / Trade-offs

- Unknown metadata falls back to decoding: optimization coverage can vary by
  upstream. Conservative fallback preserves correctness without provider assumptions.
- The matcher adds a small failure cost to uncommon shapes. Benchmark and report
  fallback costs along with common-path gains.
- Regex fast paths can mis-handle escapes/duplicates: full matching excludes
  duplicate/multiple output fields and differential tests cover escaped keys,
  nested content, invalid escapes and last-key-wins decoding.
