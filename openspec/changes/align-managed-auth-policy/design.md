# Design

`CODEX_LB_DEPLOYMENT_AUTH_POLICY` is `standard` by default and `managed` for the macOS wrapper. One pure policy module defines requirements and violations. The app uses it before destructive authentication mutations; the CLI evaluates a read-only SQLite snapshot without starting the server, migrations or background tasks. Missing/corrupt/inaccessible state is unknown, never implicitly safe.

`codex-lb auth-policy check --json` emits schema version 1, mode, requirements, boolean state, allowed and violation codes. Exit codes 0/1/2 mean allowed/denied/unknown. The wrapper calls the configured installed executable with the exact backend environment, bounded timeout, and validates the protocol and managed mode. The initialization marker remains a separate local provisioning prerequisite.

Mutation validation rejects explicit removal/disabling of required credentials while permitting incremental bootstrap/repair. Repository validation occurs before mutation and on retried credential mutations; optimistic versions remain authoritative. Rejections do not invalidate sessions or clear TOTP.

Settings expose read-only `deploymentAuthPolicy`; UI controls consume it and old clients remain protected by server validation. Guest access and password controls remain unchanged. Unknown policy output preserves the existing emergency shutdown behavior. The private initializer stops writing the guest flag and verifies it was preserved.

The opt-in setting is necessary because normal deployments support authentication modes and lifecycle operations that this managed deployment intentionally prohibits. No database schema migration is necessary. Application, static assets and wrapper scripts are released as one compatible set.
