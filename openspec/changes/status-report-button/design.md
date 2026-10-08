# Design

The report link is a deployment-only HTTPS setting. The distributed source
ships an empty `window.statusPageReportUrl` in `report-config.js`; the local
runtime copy receives the Lark form URL during the static asset installation.
The real tenant URL is kept in the private rollout record, not in source,
tests or the wheel.

Both `monitor/static/index.html` and `monitor/static/faq.html` render the same
anchor after the FAQ link. `style.css` gives it a primary-colored border and
background so it reads as an action without changing the active-page state.
The link opens a new tab and uses `noopener noreferrer`.
