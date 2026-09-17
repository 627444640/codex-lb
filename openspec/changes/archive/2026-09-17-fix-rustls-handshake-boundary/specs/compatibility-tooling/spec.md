## MODIFIED Requirements

### Requirement: TLS extension-order parity is calibrated against direct traffic

The analyzer MUST accept an optional second direct-Codex capture as a TLS
randomization reference. For HTTP JSON, HTTP SSE, and WebSocket independently,
it MUST deduplicate records from the same ClientHello, require a configurable
minimum sample count in every compared cohort, and compare invariant TLS
capability fields exactly. When invariant profiles match, it MUST summarize
pairwise extension precedence and order entropy and MUST compare the A/C order
distance against a deterministic 95% bootstrap limit derived only from the two
direct cohorts. Raw JA3 and ClientHello hashes MUST remain informational and
MUST NOT be used as the extension-order parity gate. Missing samples MUST be
reported as unobserved rather than pass.

#### Scenario: Randomized orders remain within direct variance

- **GIVEN** two sufficiently sampled direct cohorts have the same stable TLS
  profile and randomized extension orders
- **AND** the codex-lb cohort has the same stable profile and an order distance
  within the direct-derived 95% limit
- **WHEN** TLS randomization parity is analyzed
- **THEN** the transport cohort passes
- **AND** differing raw JA3 hashes remain visible as informational evidence

#### Scenario: Load balancer emits a fixed or shifted order profile

- **GIVEN** the direct cohorts demonstrate randomized extension ordering
- **AND** the codex-lb cohort emits an order distribution beyond the
  direct-derived 95% limit
- **WHEN** TLS randomization parity is analyzed
- **THEN** that transport cohort fails
- **AND** stable-profile equality does not conceal the distribution mismatch

#### Scenario: A cohort has too few independent handshakes

- **GIVEN** any direct or codex-lb cohort has fewer than the configured minimum
  deduplicated ClientHello samples
- **WHEN** TLS randomization parity is analyzed
- **THEN** that transport cohort is reported as unobserved
- **AND** it is not reported as a pass

#### Scenario: Security update changes signature capabilities

- **GIVEN** a security-updated TLS provider advertises signature algorithms absent from sufficiently sampled direct-client reference cohorts
- **WHEN** the analyzer compares invariant TLS capability profiles
- **THEN** it MUST report the signature capability mismatch
- **AND** it MUST NOT hide the mismatch as randomized extension order or waive it because the update fixes a vulnerability
