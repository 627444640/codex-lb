## 1. Contracts and integration
- [x] Add typed administrator-only Settings routes and private monitor client.
- [x] Add email alert settings and announcement controls to the existing Settings page.
- [x] Remove the independent monitor administrator surface and migrate control to the service API.

## 2. Public display
- [x] Return and show only seven-day capacity percentage, without account counts.
- [x] Persist daily availability and render a calendar heatmap with unknown-day handling.
- [x] Center announcements in a top full-width row and incidents at the bottom.

## 3. Verification and handoff
- [x] Verify LB auth/guest/write boundaries and monitor service authentication.
- [x] Verify SMTP settings persistence, secret redaction, notice lifecycle and heatmap day boundaries.
- [x] Run targeted backend and frontend checks, build and strict OpenSpec validation.
- [x] Verify integrated Settings using isolated endpoints and component interaction tests; update the independent status service and documentation.
- [x] Preserve the explicitly deferred production LB deployment boundary.

## Remaining environment acceptance
- [x] LB Settings browser interaction and visual readback at desktop/mobile widths, using an isolated backend and synthetic monitor responses.
- [ ] Production LB rollout, only after the documented deployment hold is lifted.
