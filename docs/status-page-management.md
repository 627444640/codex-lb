# Email alerts and public announcements

Normative behavior: [status-page-management specification](../openspec/specs/status-page-management/spec.md).

Administrators manage email alerts and announcements from **Settings → Email alerts and announcements**. There is no separate status-page administrator account. Guests cannot access private configuration, drafts or delivery history.

Enter SMTP server, port, TLS mode, sender, username and recipients. Enter the mailbox's SMTP authorization code once; subsequent saves may leave the code blank to retain it. The API never returns the code. Saving enabled settings allows the monitor to deliver new confirmed incident/recovery events. Existing events recorded while mail was disabled are not automatically backfilled.

Announcements support drafts, immediate or scheduled publishing, an optional end time and withdrawal. Display times are interpreted as UTC+8. The public page shows announcements in the top centered row, seven-day capacity as a percentage, readiness history as a daily calendar heatmap and incidents in the bottom full-width section.

The independent monitor uses a private server-to-server connector documented in [the capability context](../openspec/specs/status-page-management/context.md). Operators do not paste service-control tokens into the browser. The monitor can report an unhealthy LB process while its host remains alive; host-level failures require an external observer.
