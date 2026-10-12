## MODIFIED Requirements

### Requirement: Direct WebSocket replay never mixes numeric response sequences

For direct Responses WebSocket requests, the proxy MUST NOT transparently
replay a request on a fresh upstream generation after any finite integer
`sequence_number` frame for that request has been successfully sent downstream,
except for the verified no-generation prewarm case and the cached-history
anchor-loss case defined below. When an upstream close would otherwise trigger
replay, the proxy MUST settle the failed pending request without emitting
frames from a new upstream generation under the existing downstream response
id, and MUST close the downstream WebSocket with code 1011 so the client can
retry on a fresh transport. When an upstream terminal error would otherwise
trigger quota, authentication, security-work, or equivalent replay, the proxy
MUST finalize and surface that terminal error without reconnecting. Suppressed
frames and non-integer sequence sentinels MUST NOT by themselves disable
otherwise-safe replay.

The prewarm exception MUST require `request_kind = "prewarm"`, a literal
normalized `generate = false`, exactly one recorded `response.created`, no
visible output, sequence watermark `0`, a single pending request, and the
existing one-shot replay eligibility. The proxy MUST suppress the replayed
`response.created`.

The anchor-loss exception MUST require a `previous_response_not_found` terminal
for a request that carried `previous_response_id`, a one-shot replay staged from
cached conversation history, no model output, a single pending request,
recorded upstream events limited to `response.created` and
`response.in_progress`, and an exposed watermark lower than the number of
those recorded events. The proxy MUST suppress the replayed `response.created`
and, when the original turn recorded `response.in_progress`, the replayed
`response.in_progress`.

In both exceptions the proxy MUST NOT renumber or synthesize sequences. If a
later non-suppressed replay event has a finite integer sequence that does not
advance beyond the exposed watermark, the proxy MUST settle it as
`stream_incomplete`, emit no synthetic terminal frame, and close downstream
with code 1011.

#### Scenario: Sequenced response is interrupted before completion

- **WHEN** a direct WebSocket model-generating request has emitted
  `response.created` or another frame with a finite integer `sequence_number`
- **AND** upstream closes before a terminal response event
- **THEN** codex-lb does not transparently replay that request under the
  existing downstream response id
- **AND** no lower replay sequence is emitted downstream
- **AND** the downstream WebSocket closes with code 1011

#### Scenario: Prewarm metadata without generate-false body is not sufficient

- **WHEN** a direct WebSocket request claims `request_kind = "prewarm"`
- **BUT** its normalized body does not contain the literal `generate = false`
- **AND** a numeric sequence has been sent downstream
- **THEN** codex-lb does not transparently replay the request

#### Scenario: Progressed prewarm is not replayed

- **WHEN** a verified no-generation prewarm has emitted `response.created` and
  any additional `response.*` progress event
- **AND** upstream closes before completion
- **THEN** codex-lb does not transparently replay the request
- **AND** the downstream WebSocket closes with code 1011

#### Scenario: Replayed prewarm sequence must advance

- **GIVEN** a verified no-generation prewarm is replayed after exposing
  `response.created` at sequence `0`
- **WHEN** a non-suppressed replay frame has a finite integer
  `sequence_number <= 0`
- **THEN** codex-lb emits no frame from that replay generation downstream
- **AND** it settles the request as `stream_incomplete`
- **AND** it closes the downstream WebSocket with code 1011

#### Scenario: Anchor loss after a sequenced prelude replays from cached history

- **GIVEN** the history cache holds the conversation behind a direct WebSocket
  request's `previous_response_id`
- **AND** `response.created` at sequence `0` has been sent downstream with no
  model output
- **WHEN** upstream fails the turn with `previous_response_not_found`
- **THEN** codex-lb resends the turn once from cached history
- **AND** it suppresses the replayed `response.created`
- **AND** it forwards only replay numeric sequences that advance beyond `0`

#### Scenario: Anchor-loss replay sequence must advance

- **GIVEN** a cached-history anchor-loss replay was staged after a sequenced
  prelude was sent downstream
- **WHEN** a non-suppressed replay frame has a finite integer sequence at or
  below the exposed watermark
- **THEN** codex-lb emits no frame from that replay generation downstream
- **AND** it settles the request as `stream_incomplete`
- **AND** it closes the downstream WebSocket with code 1011

#### Scenario: Unsafe replay settles request ownership

- **WHEN** sequenced replay is refused after upstream close or a replay
  sequence fails to advance
- **THEN** response-create admission, account-local leases, API-key
  reservations, and request logging are finalized exactly once
- **AND** the failed attempt does not become a successful continuity owner

#### Scenario: Sequenced retryable terminal event is not replayed

- **WHEN** a direct WebSocket request has successfully emitted a finite integer
  `sequence_number`
- **AND** upstream emits a terminal error that would ordinarily trigger
  transparent quota, authentication, or security-work replay
- **THEN** codex-lb does not reconnect or resend the request
- **AND** the terminal error is finalized and remains client-visible under the
  existing error contract

#### Scenario: Sequence-free startup remains replayable

- **WHEN** upstream closes before any numeric sequence-bearing frame has been
  successfully sent downstream
- **AND** the request otherwise satisfies the existing one-shot replay guard
- **THEN** codex-lb MAY transparently replay the request on a fresh upstream
  connection

#### Scenario: Suppressed frame does not establish exposure

- **WHEN** codex-lb suppresses an upstream frame before downstream emission
- **AND** the suppressed frame contains a numeric `sequence_number`
- **THEN** that frame does not establish the downstream sequence watermark
