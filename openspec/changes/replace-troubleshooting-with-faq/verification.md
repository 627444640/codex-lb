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

Production deployment and remote publication are pending in this candidate record. They will be independently verified before this change is archived. Retired implementation files were privately archived before removal; legacy runtime settings will be archived during deployment, outside active runtime paths.
