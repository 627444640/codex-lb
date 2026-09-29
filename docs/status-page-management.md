# Status-page administration

Normative behavior: [status-page-management specification](../openspec/specs/status-page-management/spec.md).

Administrators manage email alerts and announcements from **Settings → Email alerts and announcements**. There is no separate status-page administrator account. Guests cannot access private configuration, drafts or delivery history.

Enter SMTP server, port, TLS mode, sender, username and recipients. Enter the mailbox's SMTP authorization code once; subsequent saves may leave the code blank to retain it. The API never returns the code. Saving enabled settings allows the monitor to deliver new confirmed incident/recovery events. Existing events recorded while mail was disabled are not automatically backfilled.

Announcements support drafts, immediate or scheduled publishing, an optional end time and withdrawal. Display times are interpreted as UTC+8. The public page shows announcements in the top centered row, seven-day capacity as a percentage, readiness history as a daily calendar heatmap and incidents in the bottom full-width section.

The independent monitor uses a private server-to-server connector documented in [the capability context](../openspec/specs/status-page-management/context.md). Operators do not paste service-control tokens into the browser. The monitor can report an unhealthy LB process while its host remains alive; host-level failures require an external observer.

The matching optional monitor source, locked dependencies and synthetic tests are included in [deploy/status-monitor](../deploy/status-monitor/README.md). Start it separately on loopback and keep its runtime state outside the source LB data directory. Repository seed addresses are labelled examples; customize them before publishing guides. The base LB installation does not start this companion automatically.

## Frequently asked questions

Use **Settings → Frequently asked questions** to create, search and edit error guides. Each entry includes an error identifier, title, keywords, symptoms, cause, ordered solution steps and limitations. An optional HTTP(S) address adds a copy button and prerequisites to the public entry. Content is plain text; HTML is never executed.

Lower order values appear first. Save a draft to keep content private, or save and publish to display it on the independent FAQ page. Withdraw a published entry to hide it without deleting it. The status filter includes a Deleted view: deletion is recoverable, and restoration always returns the entry to a private draft. Publish again when it is ready.

Concurrent edits are protected by revisions. A stale save is rejected instead of overwriting another administrator's changes. Preserve any unsaved text, refresh the list and reopen the latest entry before applying your changes.

The first monitor startup with this feature imports the two existing guides once. Later restarts do not reimport seeds or undo edits and deletions. The public page is `/static/faq.html`; the previous `/static/troubleshooting.html` address redirects to it with existing guide anchors preserved. It uses server-side rendering and stays readable with JavaScript disabled or status sampling unavailable. Its content database and service must still be available. Drafts and deleted entries never enter public HTML.


## Upgrade from the retired assistant

The FAQ is guide-only. The public chat, assistant configuration and model connection-test APIs, inference code and streaming assets have been removed. Loading the FAQ does not contact a model or fetch the status API.

When upgrading an existing deployment, back up the monitor state and move its former private `troubleshooting-assistant.json` configuration outside the active runtime directory. Keep any rollback copy private. The new application ignores legacy assistant configuration and usage tables; existing guide content, notices, status history and service-control credentials are preserved. Retiring this feature does not revoke the provider key or remove core Codex LB model-source features.
