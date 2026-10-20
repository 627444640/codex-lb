## 1. Reproduce
- [x] Confirm affected records are prewarm, live catalog omits Flex, and installed/source target files match.
- [x] Reproduce the failure through the WebSocket endpoint with a stub upstream.

## 2. Implement
- [x] Normalize only verified generate=false Codex prewarms before reservation.
- [x] Preserve normal turns, other tiers, supported Flex and unknown catalog semantics.
- [x] Synchronize the owning OpenSpec contracts.

## 3. Verify and deliver
- [x] Run regression, compatibility and static checks.
- [ ] Commit the isolated fix and merge into the recorded target without changing existing edits.
- [ ] Back up and deploy only the verified runtime patch, drain/restart and read back.
- [ ] Verify the installed path against live catalog evidence and observe production outcomes.
