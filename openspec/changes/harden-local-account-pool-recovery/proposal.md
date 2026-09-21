# Harden the deployed SQLite account pool without a database or authentication migration

## Why

The deployed 1.24.0 installation contains local pricing and output-timing fixes
that differ from its checkout. Recorded failures include stale response anchors,
accepted but output-free overloads and abrupt stream termination. The operator
has confirmed SQLite remains the LB backend, with the PostgreSQL knowledge
service kept independent. A database migration or complete beta upgrade is out
of scope for this change.

## What Changes

- Freeze an isolated source baseline that matches the installed application.
- Port bounded recovery and scheduling fixes only with their ownership,
  settlement and cancellation guards; retain the deployed pricing contract.
- Reproduce stale-anchor and accepted output-free recovery paths using synthetic
  upstreams. Keep account-scoped, output-bearing and ambiguous requests closed.
- Add a private SQLite/database-key snapshot and offline restore rehearsal that
  never starts a replica, refreshes credentials or calls an upstream service.
- Add bounded read-only operational observations; distinguish actual business
  validation from synthetic recovery tests and configuration status.

## Impact

Affected capabilities: responses-api-compat, account-routing, database-backends.
Existing source modifications and production files are not overwritten during
development. Account onboarding, production release and real two-Pro validation
are distinct acceptance steps. Source publication is authorized; release and
production deployment remain separate steps. The maintenance branch does not replace the newer main line.
