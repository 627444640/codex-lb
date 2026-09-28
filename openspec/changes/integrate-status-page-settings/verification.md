# Status-page source verification — 2026-09-29

The user authorized local integration into v1.24.3 alongside the independent SSE
observation optimization. This commit packages the existing LB Settings/control
integration, with formatted frontend source and no production connector credentials.

Pre-integration checks: 11 status service/API tests passed, 4 status Settings
component interaction tests passed, and scoped Python typing/lint passed. They
cover existing administrator sessions, remote unauthenticated and guest denial,
credential redaction, literal loopback destinations, redirect refusal, announcement
timezone conversion and disconnected behavior. Test values are synthetic.

The independent public monitor is a separate service; it is not moved into the LB
process. Combined branch validation, browser visual readback and any production
rollout are tracked separately. The original production rollout hold remains.
