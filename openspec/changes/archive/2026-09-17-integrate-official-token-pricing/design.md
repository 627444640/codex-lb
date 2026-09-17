## Context

The source pricing fix is based on the 1.24.0 release; current main adds an automatic pricing catalog, explicit tier-specific context prices, new request paths and a later Alembic head. Integrate only pricing and required usage evidence, preserving those newer contracts.

## Goals / Non-Goals

Goals: complete cost evidence and correct known/unknown accounting on current main.

Non-goals: importing earlier authentication, macOS tooling or metrics changes, removing active catalog refresh, changing credentials or deploying the new main branch to the local service.

## Decisions

- Adapt the verified pricing behavior to main's existing ModelPrice shape and catalog resolver. Preserve explicit active-catalog tier/context rates rather than replacing the catalog with a fixed table.
- Carry actual model, cache-write and image partitions through the current request lifecycle. Add nullable request-log evidence using a new forward migration at the current main head.
- Identify the effective price set in persisted provenance. Keep existing non-NULL historical totals unchanged, including when catalogs refresh.
- Preserve unknown-cost allowances without claiming a known final bill, and keep independently configured source prices and known-zero metadata routes distinct.
- Use current dashboard components and synthetic before/after fixtures for cost status and precision.

## Validation and merge

Run pricing/catalog, HTTP/WebSocket, image/source, quota, migration and UI regressions. Open a main-based PR, complete the actual GitHub CI and review gates, address actionable CodeRabbit threads and merge only the current validated head with a clean merge state.
