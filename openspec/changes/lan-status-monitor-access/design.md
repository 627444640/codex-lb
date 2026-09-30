# Design

The monitor stays on `127.0.0.1:2466`. This preserves the existing private
control contract: Codex LB Settings talks to a literal loopback URL with a
0600 bearer-token file, and the monitor continues to treat `/internal/*` as a
server-to-server route.

Caddy gets a separate HTTPS site on port `2467`. The site uses the existing
internal CA, accepts only the configured LAN CIDR plus loopback, returns 404
for `/internal/*`, and reverse-proxies the remaining public monitor routes to
`127.0.0.1:2466`. A dedicated host and port are used instead of a `/status`
path on the gateway site because the server-rendered HTML and browser assets
use root-relative URLs such as `/static/faq.html` and `/api/status`.

The monitor's `origin` becomes the canonical HTTPS LAN origin. An
`allowed_hosts` list covers additional LAN aliases that resolve to the same
listener. The origin and host list affect trusted-host validation and secure
cookie policy only; they do not make the loopback application listener public.

The runtime change is applied only after a private backup of the monitor
configuration and Caddyfile. Validation must cover Caddy adaptation, monitor
unit tests, the loopback connector, the LAN HTTPS page and FAQ, an external
LAN-source denial, and a direct `/internal/*` denial at the proxy. Rollback
restores the two files and reloads the existing Caddy/monitor jobs.
