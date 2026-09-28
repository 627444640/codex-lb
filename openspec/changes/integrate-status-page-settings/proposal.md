# Integrate status-page management into Codex LB settings

## Why

The independent status page currently has its own administrator login, mail configuration and announcement management. The requested product boundary is one management surface in Codex LB Settings, with a separate public status display.

## What Changes

- Add a Settings section for email alerts and announcements, protected by existing dashboard administrator access.
- Connect the Settings API to the independently running monitor through a private, loopback-only service credential. The browser never receives this credential.
- Remove the monitor's second administrator surface and expose only read-only public display routes plus the authenticated service control API.
- Display only the seven-day capacity percentage; remove account counts from the public response and page.
- Replace the availability strip with a daily calendar heatmap using Asia/Taipei day boundaries.
- Put announcements in a centered, full-width top row and incidents in a full-width bottom section.

## Impact

New `status-page-management` capability, dashboard Settings, and the separate monitor project. No LB business schema migration or proxy routing changes. On 2026-09-29 the user authorized committing this change and combining it with the independent streaming feat branch in v1.24.3. The current local project record says the v1.24.2 LB deployment is deferred; integration will be built and demonstrated with isolated data before any production LB rollout.
