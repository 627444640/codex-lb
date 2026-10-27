## Context

The cache keys include model, service tier, quota routing policies and account scope. TTL controls whether data may be returned, but the baseline dictionary retains entries until invalidation. A four-case regression reproduces retention with excessive cardinality, disabled caching and expired reads/writes.

## Goals / Non-Goals

Goals: bound resident scopes, reclaim obsolete snapshots, keep account-selection and invalidation behavior intact.

Non-goals: changing routing policy, distributed cache ownership, cache-loader single-flight or operator configuration.

## Decisions

Use insertion-ordered storage with a fixed default capacity of 256. Fixed TTL means insertion order also orders expiry; replacing an entry moves it to the end. Reads do not extend TTL. Stores remove expired oldest entries and then evict oldest entries until capacity is available. Reads and amortized expiry cleanup stay constant-time per entry.

Keep the generation check before any store mutation. Eviction does not bump generation or publish invalidation events. Keep TTL-zero reads and writes disabled. Constructor-only capacity injection makes small deterministic tests possible without adding a setting.

## Risks / Trade-offs

FIFO eviction can increase misses under scope churn. It cannot change eligibility because an evicted scope reloads through the existing selection path. The limit bounds entries, not bytes: each snapshot can still scale with account count.

## Validation

Nine new tests cover capacity, disabled retention, expired release, replacement ordering, generation fencing, invalid capacity and public selection across evicted account scopes. The combined related suites produced 131 passed, one existing skip and one existing xfail. Changed-file typing, Ruff, formatting and architecture checks pass. Windows-wide typing still reports POSIX/uvloop platform diagnostics; full Linux CI remains a separate gate.
