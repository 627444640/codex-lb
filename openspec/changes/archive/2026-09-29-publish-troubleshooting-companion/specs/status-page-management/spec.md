## ADDED Requirements

### Requirement: Paired monitor source is distributable
The repository SHALL include the independently runnable monitor component under `deploy/status-monitor/`, with its runtime source, public static resources, dependency lock and synthetic tests. Its setup instructions MUST distinguish optional companion startup from the base LB install and MUST keep monitor state separate from source LB data. Distributed files MUST exclude runtime credentials, databases, logs, captured production requests and machine-specific diagnostic reports. Seed addresses SHALL be clearly labelled examples requiring administrator customization.

#### Scenario: Operator obtains the repository
- **WHEN** an operator checks out the version containing the troubleshooting dashboard
- **THEN** the matching monitor source and test instructions are available in the same revision
- **AND** the monitor is not automatically started or configured with production credentials

#### Scenario: Existing deployment uses customized guides
- **WHEN** the source-distribution examples are updated
- **THEN** no existing runtime guide database or running service is modified
