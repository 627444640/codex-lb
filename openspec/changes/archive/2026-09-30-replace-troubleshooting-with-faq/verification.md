# FAQ-only candidate verification — 2026-09-30

- Status-page backend tests: **19 passed**, including guide administration, service control and retired assistant APIs.
- Settings and i18n frontend tests: **18 passed**, including FAQ management and the absent assistant card.
- Independent monitor tests: **39 passed**, including FAQ rendering, legacy redirects, preserved guides and retired usage state, and unavailable model APIs even when an old configuration file exists.
- FAQ clipboard/DOM tests: **2 passed**, with zero model/status network requests.
- Repository Python lint/format and type checks, relevant frontend lint/type checks and the production frontend build: passed.
- The active OpenSpec change and all **59** main specifications: strict validation passed.
- A fixed wheel and paired monitor were started with synthetic data. The FAQ route and old-link redirect worked; the assistant schema and old model APIs were absent. No model was invoked.
- The candidate application contains **683** app files and preserves the existing **71** backend dependencies.

Full `make ci` was attempted and stopped because Bun is unavailable on this host. Installed Node executables were used for the relevant frontend checks and build. No full/cloud CI success is claimed.

## Publication and deployment

The implementation was committed on the fresh `fix/faq-without-llm-20260930`
branch as `4e91d0c6`, merged into `v1.24.3` with an explicit merge commit
`1fab0649`, and both refs were pushed and read back. Publication auditing found
no private paths, site addresses or credentials in newly reachable objects.

Deployment completed on 2026-09-30 at 01:09 Asia/Taipei after idle checks,
graceful retirement of the old assistant, a verified cold backup and offline
installation. Retired implementation was archived before removal. The saved
assistant configuration was moved to a private archive outside active runtime
paths; no provider credential was revoked and no model was invoked for this
deployment.

Independent readback confirmed the FAQ heading and page, the old-address
redirect, stable published anchors, 404 responses from all five retired monitor
model routes and unavailable old stream assets. Backend assistant routes were
also unavailable. Guide/notices hashes, backend history counts, authentication
state and all 71 dependencies were preserved. Backend, HTTPS, public gateway and
monitor health checks passed, and normal admission was restored.

The native browser tool returned `cgWindowNotFound`, so no native screenshot or
pixel-level acceptance is claimed. Server-rendered HTML, clipboard/DOM behavior,
the production build and running route boundaries were verified separately.

Delivery-record finalization follows the standing workflow on a separate fresh
`fix/faq-delivery-records-20260930` branch before merging back into `v1.24.3`.
