# Design

The existing public Caddy site on port `8443` receives the Cloudflare Tunnel
traffic. A path handler for `/status/*` strips the prefix and reverse-proxies
to the loopback monitor at `127.0.0.1:2466`. `/status` redirects to
`/status/` so document-relative URLs resolve below the mount.

The monitor's index document uses `<base href="./">`; its FAQ document uses
`<base href="../">`. Static assets, status polling and FAQ links are relative
to the document base. This keeps the standalone LAN root behavior while making
the same artifacts function under `/status/` without response-body rewriting.

The public Caddy proxy sets an allowed monitor Host value (`192.168.3.182` in
the maintained deployment) because the monitor's TrustedHost middleware must
not accept the public Tunnel hostname as a new application host. The proxy
does not forward `/status/internal/*`; the monitor's loopback token boundary
remains an independent defense.

The dashboard's Service status link uses the current dashboard HTTPS origin and
the `/status/` path. It preserves the current host and port so both the public
Tunnel site and the private `8443` LAN dashboard open the same mounted monitor.
