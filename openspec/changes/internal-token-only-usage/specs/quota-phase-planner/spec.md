## ADDED Requirements

### Requirement: Internal planner retires monetary warmup budgets

The internal planner MUST NOT enforce the historical `max_warmup_credits_per_day` monetary budget against request-log costs, and its dashboard MUST NOT show that budget as an active control. The stored setting MUST remain compatible and unchanged when omitted from unrelated edits. Planner mode, time windows, forecast/evidence gates and maximum warmup counts MUST retain their behavior. The `expected_cost` decision value MUST remain a non-monetary scheduling penalty and MUST NOT be interpreted as currency or a price-weighted credit charge. Demand forecasts MUST depend on token and request measurements without weighting retained historical monetary values.

#### Scenario: Historical monetary budget does not gate warmup

- **GIVEN** an old planner monetary budget is exhausted
- **WHEN** otherwise eligible scheduled or manual warmup is evaluated
- **THEN** mode, schedule, evidence and count limits still govern the decision
- **AND** the monetary budget neither blocks nor prices the work

#### Scenario: Scheduling penalty remains diagnostic

- **WHEN** a planner decision exposes `expected_cost`
- **THEN** it describes the existing non-monetary scheduling penalty
- **AND** it does not generate or enforce a monetary amount

## MODIFIED Requirements

### Requirement: Quota phase planner defaults are non-invasive

The quota phase planner SHALL default to audit-only behavior. Fresh installations
MUST enable non-monetary routing penalties and scheduler audit rows without sending synthetic
traffic, and the planner MUST skip work instead of blocking user traffic when
forecast, usage, or warmup-effect data is stale, missing, or uncertain.

#### Scenario: Fresh installs do not send warmup traffic

- **GIVEN** the service starts with default quota planner settings
- **WHEN** the scheduler evaluates a planner tick
- **THEN** it may write shadow or no-op decision rows
- **AND** it MUST NOT send synthetic warmup traffic

#### Scenario: Uncertain planner data is non-blocking

- **GIVEN** planner input data is stale, missing, or uncertain
- **WHEN** routing or scheduler planning evaluates accounts
- **THEN** real user requests remain eligible according to the normal hard
  account gates
- **AND** scheduler actions are skipped or recorded as audit decisions instead
  of burning quota

### Requirement: Warmup decisions are claimed before synthetic traffic

Warmup execution SHALL atomically transition a planned decision to `executing`
before reserving API-key budget or sending synthetic probe traffic, and that
transition SHALL be the single authoritative enforcement point for the daily
warmup count budget: the claim statement MUST evaluate the
`planned` status precondition and count guard atomically, so concurrent
claimants on other replicas or processes cannot exceed that budget. The
count-budget guard MUST include in-flight `executing` warmup decisions in
addition to `executed` ones, so a probe reserves budget when it is claimed
rather than after it completes. The claim MUST record its own timestamp on the
decision, and in-flight `executing` decisions MUST count against the budget
day in which they were claimed — not the day the decision row was created —
so a decision planned before the daily boundary but claimed after it consumes
the claim day's budget. On PostgreSQL, concurrent claims MUST be
serialized (a transaction-scoped advisory lock on a fixed warmup-budget key)
so two claims cannot both evaluate the budget against a stale snapshot; on
SQLite the claim MUST execute as a single statement under the database-level
writer lock. When a claim is refused because a budget guard failed, the
decision MUST be skipped with the exhausted-count-budget reason. The retained monetary
credit-budget setting MUST NOT be read or enforced as an admission guard. Final outcomes such as `executed`,
`failed`, or API-key skip reasons MUST only update decisions that are still
`executing`. Cancellation MUST only update decisions that are still `planned`
or `skipped` and MUST NOT cancel an in-flight `executing` decision.

#### Scenario: Planned warmup is claimed before probe send

- **GIVEN** a planned warmup decision is eligible to run
- **WHEN** warm-now starts sending the synthetic probe
- **THEN** the persisted decision status is already `executing`
- **AND** a concurrent worker cannot claim the same planned decision

#### Scenario: Concurrent claims cannot exceed the daily count budget

- **GIVEN** two replicas each hold a planned warmup decision
- **AND** one warmup remains in the daily count budget
- **WHEN** both replicas execute warm-now concurrently
- **THEN** exactly one decision transitions to `executing` and sends a probe
- **AND** the other decision is skipped with reason
  `daily_warmup_count_budget_exhausted`

#### Scenario: In-flight executing warmups reserve count budget

- **GIVEN** a warmup decision claimed today is still `executing`
- **AND** the daily count budget allows one warmup
- **WHEN** another replica attempts to claim a planned warmup decision
- **THEN** the claim is refused
- **AND** the planned decision does not transition to `executing`

#### Scenario: Warmup planned yesterday but claimed today consumes today's budget

- **GIVEN** a warmup decision the scheduler persisted before the daily boundary
  with a future `scheduled_at`
- **AND** the daily count budget allows one warmup
- **WHEN** the decision is claimed after the daily boundary
- **THEN** the claimed `executing` decision counts against the new day's budget
- **AND** a subsequent claim of another planned decision on the same day is
  refused

#### Scenario: Dormant monetary budget does not prevent a claim

- **GIVEN** historical warmup request costs exceed the retained monetary budget
- **WHEN** a planned warmup satisfies the count, mode, time and safety gates
- **THEN** the historical monetary budget does not reject its claim
- **AND** no monetary estimate is generated for the probe

#### Scenario: Executing warmup cannot be canceled

- **GIVEN** a warmup decision is already `executing`
- **WHEN** an operator requests cancellation
- **THEN** the decision remains `executing`
- **AND** the response reports that the decision is not cancelable
