# Retirement decision — 2026-09-30

The maintainer explicitly replaced the chat-enabled troubleshooting experience with a guide-only FAQ page and authorized publication plus service restart. The assistant implementation is **deprecated** as of this change. Its historical source remains in the parent commit and prior archived OpenSpec changes; a private archive is made before removing active files.

The existing `/static/troubleshooting.html` address redirects to the new FAQ address; individual `error-*` anchors and the guide database stay stable. Existing assistant settings are not loaded by the new application. Deployment moves that private configuration outside the active runtime directory for rollback, without printing its contents, revoking the provider key or deleting historical usage data.

This same change records the maintainer's new standing instruction: every requested modification begins on a fresh `fix/` branch and is merged back to its starting branch after validation. It does not create an automatic push or PR policy beyond the user's requested scope.
