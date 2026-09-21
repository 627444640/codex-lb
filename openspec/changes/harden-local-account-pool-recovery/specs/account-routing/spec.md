## ADDED Requirements

### Requirement: Sustained overload avoidance preserves routing ownership

The balancer SHALL use bounded recent overload evidence to avoid repeatedly
sending fresh eligible requests to an overloaded account when a healthy sibling
exists. Ordinary successful turns SHALL NOT silently erase the entire recent
overload window. Temporary overload avoidance SHALL distinguish a soft routing
preference from a hard response/file/session owner. Temporary substitutes MUST
not accidentally destroy recoverable soft affinity; hard ownership, key scope,
model support, quota and existing budget gates remain authoritative.

#### Scenario: Fresh requests avoid repeated overload while pinned requests retain their boundary
- **GIVEN** an overloaded account and an otherwise eligible healthy sibling
- **WHEN** a fresh unbound request is selected
- **THEN** bounded overload avoidance prefers a healthy eligible account
- **AND** it does not turn an account-owned continuation into a portable request

### Requirement: Confirmed quota reset recovery uses the blocking window's evidence

A rate-limited paid account MAY recover before a predicted deadline when fresh
evidence proves the specific blocking quota window reset and no current sibling
window remains exhausted. Unrelated resets, stale records and reauthentication
failures MUST NOT release the account through this exception.

#### Scenario: Early reset of the actual blocking window restores eligibility
- **GIVEN** matching post-block reset evidence and no exhausted live sibling window
- **WHEN** the usage scheduler reconciles the account
- **THEN** quota recovery can restore it without waiting for an obsolete prediction

### Requirement: Temporary substitutes keep soft affinity stable within the eligible pool

A retained soft owner under sustained overload MUST keep its ownership mapping
and use a deterministic per-thread substitute among candidates admitted by the
actual strategy and its health, model, key-scope, budget and quota gates. TTL
freshness MUST be preserved where retention is authorized. Unrecoverable or
out-of-scope owners and explicit reallocation MUST follow the existing release
rules; ambiguity-preserved mappings MUST not acquire new mutation authority.
Weighted strategies MAY discount recent account-attributable error outcomes
using a bounded ten-minute window, a ten-outcome minimum, and a nonzero weight
floor. Operators MUST be able to disable isolation or this discount separately.

#### Scenario: Repeated turns preserve one temporary substitute and return home
- **GIVEN** a recoverable isolated soft owner and an unchanged eligible pool
- **WHEN** multiple turns select a replacement
- **THEN** the thread selects a stable eligible substitute and retains its original mapping
- **AND** it can return to the original owner when isolation expires
