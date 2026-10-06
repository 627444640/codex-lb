# Add a dashboard link to the service status page

## Why

Operators need a direct way to open the LAN service status page from the
dashboard header. The existing status page is served by the companion monitor
on the same host over HTTPS port 2467.

## What Changes

- Add a `服务状态` / `Service status` link immediately after the Advanced
  navigation control in the desktop header.
- Add the same link after the Advanced section in the mobile navigation sheet.
- Derive the link from the dashboard's current hostname, force HTTPS, switch
  to port 2467 and open it in a new tab.
- Add localized labels and navigation regression coverage.

## Impact

This is a dashboard navigation change only. It does not add a dashboard route,
change authentication, expose the monitor control API, or alter the monitor
deployment. The status page remains a separate read-only LAN surface.
