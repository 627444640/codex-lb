## ADDED Requirements

### Requirement: Verbatim SSE observation preserves content-based samples without full decoding

For canonically framed HTTP/SSE output deltas within the bounded fast-observation subset, with a single unescaped top-level
`delta`, `arguments` or `input` string and supported flat metadata, timing
observation MUST determine whether that string is empty without decoding the JSON
object. Empty strings MUST NOT advance output count or first-output time. Nonempty
strings, including escaped and non-ASCII content, MUST produce the same timing
evidence as the existing parsed observation. The forwarded frame MUST remain
byte-for-byte unchanged.

Payloads outside the proven shape, including unknown or nested metadata,
duplicate/escaped content keys, non-string content, multiple content fields and
malformed JSON or payloads beyond the fast-observation bounds, MUST retain the existing parser's observation result. The
optimization MUST NOT change TTFT, reasoning handling, the 100 ms/two-nonempty-chunk
eligibility policy, terminal timing, routing or usage-settlement behavior.

#### Scenario: Long canonical output has bounded full parsing
- **GIVEN** a canonical text stream has established TTFT
- **WHEN** 256 additional supported nonempty delta frames arrive
- **THEN** observation counts all nonempty outputs without 256 JSON-object decodes
- **AND** the first-output timestamp and forwarded frames match the parsed baseline

#### Scenario: Empty output after reasoning remains unobserved
- **GIVEN** a reasoning delta establishes TTFT before any non-reasoning output
- **WHEN** empty canonical output frames arrive before the first nonempty output
- **THEN** empty frames neither increment the sample count nor establish first-output time
- **AND** the first nonempty content establishes the same timestamp as parsed observation

#### Scenario: Ambiguous payload retains decoder semantics
- **GIVEN** a canonical payload contains duplicate or escaped output keys, nested
  metadata, non-string values, or malformed JSON
- **WHEN** timing observation runs
- **THEN** it uses the existing parser and produces identical timing evidence
- **AND** forwarding and error-handling behavior remain unchanged
