# Status-page administration

Normative behavior: [status-page-management specification](../openspec/specs/status-page-management/spec.md).

Administrators manage email alerts and announcements from **Settings → Email alerts and announcements**. There is no separate status-page administrator account. Guests cannot access private configuration, drafts or delivery history.

Enter SMTP server, port, TLS mode, sender, username and recipients. Enter the mailbox's SMTP authorization code once; subsequent saves may leave the code blank to retain it. The API never returns the code. Saving enabled settings allows the monitor to deliver new confirmed incident/recovery events. Existing events recorded while mail was disabled are not automatically backfilled.

Announcements support drafts, immediate or scheduled publishing, an optional end time and withdrawal. Display times are interpreted as UTC+8. The public page shows announcements in the top centered row, seven-day capacity as a percentage, readiness history as a daily calendar heatmap and incidents in the bottom full-width section.

The independent monitor uses a private server-to-server connector documented in [the capability context](../openspec/specs/status-page-management/context.md). Operators do not paste service-control tokens into the browser. The monitor can report an unhealthy LB process while its host remains alive; host-level failures require an external observer.

The matching optional monitor source, locked dependencies and synthetic tests are included in [deploy/status-monitor](../deploy/status-monitor/README.md). Start it separately on loopback and keep its runtime state outside the source LB data directory. Repository seed addresses are labelled examples; customize them before publishing guides. The base LB installation does not start this companion automatically.

## Troubleshooting guides

Use **Settings → Troubleshooting guides** to create, search and edit error guides. Each entry includes an error identifier, title, keywords, symptoms, cause, ordered solution steps and limitations. An optional HTTP(S) address adds a copy button and prerequisites to the public entry. Content is plain text; HTML is never executed.

Lower order values appear first. Save a draft to keep content private, or save and publish to display it on the independent troubleshooting page. Withdraw a published entry to hide it without deleting it. The status filter includes a Deleted view: deletion is recoverable, and restoration always returns the entry to a private draft. Publish again when it is ready.

Concurrent edits are protected by revisions. A stale save is rejected instead of overwriting another administrator's changes. Preserve any unsaved text, refresh the list and reopen the latest entry before applying your changes.

The first monitor startup with this feature imports the two existing guides once. Later restarts do not reimport seeds or undo edits and deletions. The public page retains `/static/troubleshooting.html`, uses server-side rendering and stays readable with JavaScript disabled or status sampling unavailable. Its content database and service must still be available. Drafts and deleted entries never enter public HTML.

## Troubleshooting assistant

Administrators configure the assistant in **Settings → Troubleshooting assistant**. Enter the existing Codex LB `/v1` base URL, an authorized model and a dedicated API key. HTTP is permitted for a local gateway; remote addresses require verified HTTPS. Save the configuration, use **Test saved model**, then enable the assistant when ready. Testing makes a real generation request and counts toward the daily request budget. Changing the destination requires re-entering the key; leaving it blank otherwise preserves the saved secret.

The default model is `mercury-2.5`. Only one model ID can be saved, including while the assistant is disabled; saving another replaces the previous selection for subsequent chat and test requests. Do not enter a model list or separate names with spaces, commas or semicolons. The gateway must recognize the exact ID and authorize it for the configured key. Existing non-empty model selections remain in place; older unconfigured blank selections use the new default. Visitors cannot select or override the model.

Visitors can paste a text error above the guide list and press Enter; Shift+Enter adds a newline. Retrieval uses error identifiers, keywords and Chinese text fragments from current published guides. Up to three bounded excerpts are supplied to the model. The answer includes server-validated source links; a question without matching evidence asks for clarification without a model call. These are suggestions based on guides, not a live inspection of the visitor's system.

The monitor does not persist questions or answers. Short follow-up context stays in page memory and is bounded on each request. Common credential patterns are redacted before transmission, but visitors should still avoid pasting secrets. The model receives no database, shell or management tools. Its text is displayed as plain text, and changed or withdrawn source revisions invalidate an in-flight answer.

The assistant defaults off. Limits include 2,000 characters per question, four history messages, two concurrent model calls per process, a per-peer rate limit and a durable daily model-call budget using Asia/Taipei dates. Proxied visitors may share a peer limit. The assistant requests `max_completion_tokens: 2048` through the Chat Completions source route, but provider compatibility and request budgets still require validation. Use a dedicated quota-limited key in addition to the assistant's time, response-size, concurrency and request-count limits.

The existing guide page remains readable while the model is disabled, unconfigured or unavailable. Authentication or model errors are sanitized; visitors never receive the saved key or private configuration.

### Streaming diffusion

Configure a gateway model source supporting Chat Completions, streaming, `diffusing: true` and JSON-schema output. The official Mercury model ID is `mercury-2.5`; retain a different ID only when it is a configured gateway alias. The assistant still saves exactly one model.

The chat replaces provisional text as real provider snapshots arrive. Drafts are labelled as being generated and may change. Source links and follow-up history are committed only after final validation. Stop generation cancels the request; failed or truncated drafts are removed and do not become previous assistant messages.

Some gateway keys with usage limits buffer external streams until accounting is complete, which delays visible diffusion. The integration preserves this policy. Verify first-snapshot timing with the actual authorized key and proxy path; protocol tests or a synthetic fixture are not real Mercury acceptance.
