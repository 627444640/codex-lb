## 1. Scope and safety
- [x] Reconcile the source baseline and production separation.
- [x] Define token-only, telemetry removal, IP, and historical-data preservation contracts.
- [x] Prepare isolated Python/frontend tooling and guarded test launchers.

## 2. Anonymous telemetry removal
- [x] Remove collector modules, lifecycle hooks, API routes and configuration fields.
- [x] Remove dashboard controls, consent/preview components, client requests and strings.
- [x] Preserve historical database migrations and inert legacy columns.
- [x] Add regression coverage for absent routes/tasks/network and unchanged ordinary settings/data.

## 3. Token-only accounting
- [x] Stop request price estimation and new monetary values while retaining token evidence.
- [x] Retire cost and price-weighted credit limits without deleting historical records or weakening token limits.
- [x] Preserve stored model-source prices during ordinary edits with omitted price fields.
- [x] Remove monetary displays/inputs from usage, reports, API-key and model-source UI.
- [x] Validate token counters, settlement and historical-data preservation.

## 4. Client IP visibility
- [x] Complete existing trusted-IP propagation on client-originated proxy operations.
- [x] Expose client IP as a normal request-log column while preserving guest redaction.
- [x] Validate direct/trusted/untrusted/missing IP and background-task null behavior.

## 5. Validation and documentation
- [x] Update normative specs, rendered documentation and generated settings reference.
- [x] Run focused backend/frontend tests, static checks and isolated browser smoke.
- [x] Build and inspect a fresh package; verify migration graph/schema compatibility.
- [x] Independently review the completed diff and confirm production remains unchanged.
- [x] Record exact checks, limitations and the separate deployment boundary.

## 6. Separate operational acceptance (not executed)
- [ ] If explicitly authorized, perform a backed-up, drained production rollout and validate real authenticated clients, including LAN/Tunnel source IP and existing WebSocket behavior.
