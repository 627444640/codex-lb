# Expose the read-only status page on the public site

## Why

The status monitor currently has a private LAN HTTPS entrypoint on port
`2467`. Mobile clients that reach the service through the existing public
Cloudflare site cannot use that port, and many mobile devices do not trust the
deployment's private Caddy CA. Operators need the same read-only status page
under the public site's normal HTTPS origin.

## What Changes

- Serve the status monitor at `/status/` through the existing public site.
- Make the monitor's public HTML and JavaScript work from both `/` and the
  `/status/` mount by using document-relative resource and navigation URLs.
- Keep monitor control paths private: the public proxy returns `404` for
  `/status/internal/*` before forwarding any request.
- Document the public entrypoint and preserve the existing LAN `2467` entry.

## Impact

The public surface remains read-only status, FAQ, announcements and bounded
aggregates. The monitor process remains on `127.0.0.1:2466`; only the existing
Caddy/Tunnel site gains a path proxy. No dashboard authentication, model route,
or Settings connector behavior changes.
