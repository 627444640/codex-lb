# admin-auth Specification

## Purpose

Define dashboard authentication behavior so login, bootstrap, TOTP, and session handling stay secure and predictable.
## Requirements
### Requirement: Login rate limiting

The system SHALL rate-limit failed password login attempts using the existing `TotpRateLimiter` pattern: maximum 8 failures per 60-second window. On rate limit breach, the system MUST return 429 with a `Retry-After` header. Requests rejected because password login is not configured MUST NOT consume that failed-login budget.

#### Scenario: Rate limit triggered

- **WHEN** 8 failed login attempts occur within 60 seconds
- **THEN** the 9th attempt returns 429 with `Retry-After` header indicating seconds until the window resets

#### Scenario: Rate limit resets on success

- **WHEN** a successful login occurs after failed attempts
- **THEN** the failure counter for that client resets to zero

#### Scenario: Unconfigured password login does not spend rate-limit budget

- **WHEN** no password is configured and a login request is submitted
- **THEN** the system returns `password_not_configured`
- **AND** it does not consume one of the failed-login attempts for that client

### Requirement: Password length is bounded by bcrypt's input limit

The system SHALL enforce both a minimum and a maximum length on dashboard passwords submitted to `POST /api/dashboard-auth/password/setup` and to the `new_password` field of `POST /api/dashboard-auth/password/change`. The maximum length MUST be measured against the UTF-8 encoded byte length of the password (matching bcrypt's internal limit), not against the codepoint count, and MUST be set to exactly 72 bytes.

#### Scenario: Setup rejects passwords longer than 72 bytes

- **WHEN** `POST /api/dashboard-auth/password/setup` receives a password whose UTF-8 encoded length exceeds 72 bytes
- **THEN** the system returns HTTP 422 with error code `password_too_long`
- **AND** the response message references the 72-byte limit so the client can render it

#### Scenario: Setup accepts passwords up to 72 bytes inclusive

- **WHEN** `POST /api/dashboard-auth/password/setup` receives a password whose UTF-8 encoded length is exactly 72 bytes
- **THEN** the system accepts the password and configures it

#### Scenario: Length is measured in UTF-8 bytes, not codepoints

- **WHEN** `POST /api/dashboard-auth/password/setup` receives a password whose codepoint count is below 72 but whose UTF-8 encoded length exceeds 72 bytes (e.g. an emoji-only string)
- **THEN** the system returns HTTP 422 with error code `password_too_long`

#### Scenario: Change applies the same upper bound to the new password

- **WHEN** `POST /api/dashboard-auth/password/change` receives a `new_password` whose UTF-8 encoded length exceeds 72 bytes
- **THEN** the system returns HTTP 422 with error code `password_too_long` before attempting to hash the password

### Requirement: Dashboard password sessions use a configurable absolute lifetime

The system SHALL issue dashboard password-authenticated sessions with an absolute lifetime controlled by persisted dashboard settings. The default persisted lifetime SHALL be 1 year. Configured lifetimes at or below 30 days SHALL apply to newly issued dashboard password sessions by setting both the encrypted session expiry payload and the cookie `Max-Age` to the same value. Configured lifetimes above 30 days SHALL apply only in standard dashboard auth mode when the request is socket-level local, or when an explicit loopback-host-header override is enabled, the request uses a loopback dashboard URL, and every field value of every forwarded client-IP header is empty. Non-loopback, proxy-aware, trusted-header, or bridge-without-override requests MUST receive a 12-hour effective lifetime without rewriting the persisted setting.

#### Scenario: Newly issued dashboard password session honors configured lifetime

- **WHEN** an admin configures a dashboard session lifetime and successfully completes password authentication from a socket-level local request
- **THEN** the newly issued dashboard session expires after the configured absolute lifetime
- **AND** the cookie `Max-Age` matches the same configured lifetime

#### Scenario: Long localhost-published bridge session requires explicit override

- **WHEN** an admin configures a dashboard session lifetime greater than 30 days and successfully completes password authentication through a loopback dashboard URL whose socket peer is not loopback
- **AND** the explicit loopback-host-header override is disabled
- **THEN** the newly issued dashboard session expires after 12 hours

#### Scenario: Long localhost-published bridge session can opt in

- **WHEN** an admin configures a dashboard session lifetime greater than 30 days and successfully completes password authentication through a loopback dashboard URL whose socket peer is not loopback
- **AND** the explicit loopback-host-header override is enabled
- **AND** every field value of every forwarded client-IP header is empty
- **THEN** the newly issued dashboard session expires after the configured absolute lifetime

#### Scenario: Later duplicate forwarded client identity disables the long session override

- **WHEN** a non-loopback socket peer authenticates through a loopback dashboard URL with the explicit loopback-host-header override enabled
- **AND** a forwarded client-IP header contains an empty first field followed by a non-empty field
- **THEN** the newly issued dashboard session expires after 12 hours
- **AND** the cookie `Max-Age` is `43200`

#### Scenario: Long dashboard password session falls back for non-loopback access

- **WHEN** an admin configures a dashboard session lifetime greater than 30 days and successfully completes password authentication from a non-loopback, proxy-aware, or trusted-header request
- **THEN** the newly issued dashboard session expires after 12 hours
- **AND** the cookie `Max-Age` is `43200`

#### Scenario: Existing dashboard sessions keep their original expiry

- **WHEN** an admin changes the configured dashboard session lifetime after a session cookie has already been issued
- **THEN** previously issued cookies continue to expire according to the expiry embedded in their encrypted payload
- **AND** only newly issued dashboard password sessions use the updated lifetime

### Requirement: Dashboard OAuth callback errors hide internal exception details

Dashboard OAuth manual-callback responses MUST NOT include raw unexpected
exception strings, stack traces, local file paths, or other internal diagnostic
text in the response body. The server MAY log unexpected exceptions for operator
troubleshooting. User-actionable OAuth provider errors MAY continue to expose the
explicit provider-facing error code/message.

#### Scenario: Unexpected manual callback exception is sanitized

- **GIVEN** a dashboard session is authorized
- **AND** the OAuth manual-callback service raises an unexpected exception whose
  message contains internal diagnostic text
- **WHEN** the client calls `POST /api/oauth/manual-callback`
- **THEN** the response returns HTTP 500 with error code `manual_callback_failed`
- **AND** the response message is a generic internal-error message
- **AND** the response body does not contain the raw exception text

#### Scenario: OAuth provider error remains user-actionable

- **GIVEN** a dashboard session is authorized
- **AND** the OAuth manual-callback service raises `OAuthError` with an explicit
  error code and message
- **WHEN** the client calls `POST /api/oauth/manual-callback`
- **THEN** the response exposes that OAuth error code and message to the client

### Requirement: Dashboard guest access is read-only

The system SHALL support a dashboard `guest` role with read permission and without write permission. The system SHALL continue to treat password-authenticated, trusted-header, disabled-auth, and local bootstrap users as `admin` principals with read and write permissions.

#### Scenario: Guest can read dashboard APIs

- **WHEN** guest access is enabled and a guest principal requests a dashboard GET endpoint
- **THEN** the request succeeds using read-only dashboard access
- **AND** the session response identifies the principal as `guest`
- **AND** the session response includes only the `read` permission

#### Scenario: Guest cannot mutate dashboard state

- **WHEN** guest access is enabled and a guest principal requests a dashboard mutating endpoint
- **THEN** the system returns HTTP 403 with error code `read_only_access`
- **AND** no dashboard state is changed

### Requirement: Guest access may be enabled without a guest password

The system SHALL allow operators to enable guest access without configuring a guest password. When guest access is enabled and no guest password is configured, remote dashboard requests that do not have an admin session SHALL be authorized as a `guest` principal for read-only routes.

#### Scenario: Passwordless guest reads remotely

- **WHEN** guest access is enabled
- **AND** no guest password is configured
- **AND** a remote request has no admin dashboard session
- **THEN** dashboard GET endpoints treat the request as a `guest`

#### Scenario: Passwordless guest still cannot write

- **WHEN** guest access is enabled without a guest password
- **AND** a remote request has no admin dashboard session
- **THEN** dashboard mutating endpoints return HTTP 403 with error code `read_only_access`

### Requirement: Guest access may require a guest password

The system SHALL allow operators to configure a separate guest password. When guest access is enabled and a guest password is configured, unauthenticated remote dashboard requests SHALL remain blocked until the guest password login endpoint issues a guest session.

#### Scenario: Password-protected guest login succeeds

- **WHEN** guest access is enabled with a guest password
- **AND** a remote client submits the correct guest password
- **THEN** the system issues a dashboard session with role `guest`
- **AND** subsequent dashboard GET endpoints are allowed

#### Scenario: Password-protected guest write is denied

- **WHEN** a password-authenticated guest session requests a dashboard mutating endpoint
- **THEN** the system returns HTTP 403 with error code `read_only_access`

### Requirement: Legacy default dashboard session TTL migration

The migration for this change MUST update `dashboard_settings.dashboard_session_ttl_seconds` from `43200` to `31536000` only for rows that still carry the legacy default value. Rows with any customized value MUST remain unchanged.

#### Scenario: Legacy default row migrates to 1 year

- **GIVEN** a dashboard settings row has `dashboard_session_ttl_seconds = 43200`
- **WHEN** the migration runs
- **THEN** the row has `dashboard_session_ttl_seconds = 31536000`

#### Scenario: Customized row remains unchanged

- **GIVEN** a dashboard settings row has `dashboard_session_ttl_seconds = 7200`
- **WHEN** the migration runs
- **THEN** the row still has `dashboard_session_ttl_seconds = 7200`

### Requirement: Security-bearing dashboard settings converge across replicas
Mutations to security-bearing dashboard settings (dashboard password hash, guest access and guest password, TOTP requirement, proxy API-key auth toggle) MUST durably bump the `settings` cache-invalidation namespace before the mutation response is returned, and every replica MUST re-read the settings row within the invalidation-bus poll bound. The per-process settings cache TTL (5s) is the documented fallback bound when a bump is lost.

#### Scenario: Enabling API-key auth on one replica is enforced on peers within one poll cycle

- **GIVEN** two replicas share one database and each runs the cache-invalidation poller
- **AND** replica B's settings cache was refreshed just before the change
- **WHEN** bootstrap or a settings mutation served by replica A sets a dashboard password and enables proxy API-key auth
- **THEN** after replica B's next poll cycle, replica B's settings cache reflects the new password hash and API-key auth toggle
- **AND** replica B rejects keyless proxy requests and unauthenticated dashboard requests without waiting for the settings TTL to expire

### Requirement: Trusted proxy client identity resists appended Forwarded chain spoofing

When proxy-header trust is enabled and the socket peer belongs to a configured trusted proxy CIDR, the system MUST resolve an RFC 7239 `Forwarded` client chain from right to left. It MUST advance toward an earlier `for=` hop only while the immediately downstream peer is trusted. Every forwarded element MUST contain exactly one valid IP `for=` node, optionally with a valid port. Every parameter name and value MUST follow RFC 7239 token or quoted-string syntax, and no parameter name may repeat within an element. IPv6 nodes MUST be bracketed and quoted, and every node carrying a port MUST be quoted; numeric ports MUST contain one to five ASCII digits and fall within `0..65535`. Otherwise the entire `Forwarded` value MUST fail closed and MUST NOT classify the request as local.

`X-Real-IP`, `True-Client-IP`, and `CF-Connecting-IP` MUST each occur at most once. Repetition of any such singleton client-IP header MUST return no resolved client IP and MUST NOT classify the request as local.

#### Scenario: Client-preseeded loopback value cannot bypass remote bootstrap protection

- **WHEN** a trusted socket proxy appends `for=203.0.113.24` to a client-supplied `Forwarded: for=127.0.0.1` value
- **THEN** the resolved client is `203.0.113.24`
- **AND** the request is not classified as local

#### Scenario: Proxy appends a separate Forwarded field

- **WHEN** a client supplies `Forwarded: for=127.0.0.1`
- **AND** a trusted socket proxy appends a second `Forwarded: for=203.0.113.24` field
- **THEN** the system combines both field values in arrival order
- **AND** resolves the client as `203.0.113.24`
- **AND** does not classify the request as local

#### Scenario: Complete trusted multi-proxy chain resolves the originating client

- **WHEN** the socket peer and each downstream proxy hop belong to configured trusted proxy CIDRs
- **AND** the `Forwarded` elements contain one valid IP `for=` node per hop
- **THEN** the system resolves the originating client IP from the earliest reachable element

#### Scenario: Malformed or incomplete Forwarded chain fails closed

- **WHEN** any `Forwarded` element has a missing, duplicate, obfuscated, unknown, or malformed `for=` node
- **THEN** trusted proxy client resolution returns no client IP from that header
- **AND** the request is not classified as local

#### Scenario: Unquoted IPv6 or port-bearing node fails closed

- **WHEN** a `Forwarded` element contains an unquoted bracketed IPv6 node or an unquoted node with a port
- **THEN** trusted proxy client resolution returns no client IP from that header
- **AND** the request is not classified as local

#### Scenario: Bracketed IPv6 node with port is resolved

- **WHEN** a trusted socket proxy supplies a valid quoted bracketed IPv6 `for=` node with a numeric port
- **THEN** the system resolves the IPv6 address without the brackets or port

#### Scenario: Repeated singleton client-IP header fails closed

- **WHEN** a trusted socket request contains more than one field for `X-Real-IP`, `True-Client-IP`, or `CF-Connecting-IP`
- **THEN** trusted proxy client resolution returns no client IP
- **AND** the request is not classified as local

### Requirement: Trusted-proxy locality requires trusted socket provenance

When proxy-header trust is enabled, the system MUST classify a forwarded loopback client as local only when the raw socket peer belongs to a configured trusted-proxy CIDR and forwarded client resolution succeeds. The mere presence of a forwarded client-IP header from an untrusted socket peer MUST NOT establish locality or bypass remote dashboard bootstrap requirements.

#### Scenario: Untrusted loopback proxy cannot bypass remote bootstrap

- **WHEN** proxy-header trust is enabled
- **AND** the raw loopback socket peer is outside every configured trusted-proxy CIDR
- **AND** the request supplies a local Host header and a forwarded client-IP header
- **THEN** the request is classified as remote
- **AND** first-run password setup requires the configured bootstrap token

#### Scenario: Trusted proxy may forward a loopback client

- **WHEN** proxy-header trust is enabled
- **AND** the raw socket peer belongs to a configured trusted-proxy CIDR
- **AND** valid forwarded client resolution yields a loopback address
- **AND** the Host header is local
- **THEN** the request is classified as local

### Requirement: Direct locality inspects every forwarded client hint field

When proxy-header trust is disabled, the system MUST classify a loopback socket peer with a local Host as local only when no non-empty forwarded client-IP field value is present. When such a header occurs more than once, the system MUST inspect every field value rather than only the first.

#### Scenario: Later duplicate forwarded hint prevents local bootstrap

- **WHEN** proxy-header trust is disabled
- **AND** a loopback request with a local Host contains an empty `X-Forwarded-For` field followed by a non-empty `X-Forwarded-For` field
- **THEN** the request is classified as remote
- **AND** first-run password setup requires the configured bootstrap token

### Requirement: Trusted-proxy locality requires raw-peer identity consensus

When proxy-header trust is enabled, locality decisions used by dashboard bootstrap and disabled API-key authentication MUST evaluate trusted-proxy source membership against the launcher-preserved raw socket peer. If that peer is unavailable, the request MUST NOT establish proxy-derived locality. For a trusted peer, every allowed identity family among `X-Forwarded-For`, `Forwarded`, `X-Real-IP`, `True-Client-IP`, and `CF-Connecting-IP` that contains a non-whitespace value MUST be resolved independently with its established validation and trusted-hop behavior. The request MUST use a header-derived identity only when every populated family resolves successfully to the same IP. A malformed or unresolvable populated family, or differing resolved IPs, MUST fail closed and MUST NOT classify the request as local. Empty-only families MUST be ignored; same-family chain and singleton-duplicate behavior MUST remain unchanged. Untrusted raw peers and generic resolver callers MUST retain their established behavior.

#### Scenario: Redundant proxy families agree

- **WHEN** a trusted raw peer supplies multiple populated identity families that independently resolve to the same IP
- **THEN** locality uses that IP
- **AND** common `X-Forwarded-For` plus `CF-Connecting-IP` or `X-Real-IP` combinations remain valid

#### Scenario: Proxy families disagree or are invalid

- **WHEN** a trusted raw peer supplies populated families that resolve to different IPs, or any populated family cannot be resolved
- **THEN** the request is not classified as local

#### Scenario: Empty and repeated fields retain family behavior

- **WHEN** a family is empty-only, a chain family is repeated, or a singleton family is duplicated
- **THEN** empty-only evidence is ignored
- **AND** established chain combination and singleton duplicate rejection still apply

#### Scenario: Untrusted peer and generic resolver behavior are unchanged

- **WHEN** the raw peer is untrusted or a caller uses the generic client-IP resolver
- **THEN** the existing socket-identity or header-precedence behavior applies without locality consensus

### Requirement: Guest conversation reads require an admin principal

Conversation list and detail routes are not guest-safe dashboard reads and MUST
require an `admin` principal. Existing guest-safe GET behavior and the existing
read-only write restrictions SHALL remain unchanged.

#### Scenario: Guest cannot read conversations

- **WHEN** a guest principal requests `GET /api/conversations`, `GET /api/conversations/`, or `GET /api/conversations/{id}`
- **THEN** the system returns HTTP 403 with error code `admin_access_required`
- **AND** no conversation list or detail payload is returned

#### Scenario: Admin can read conversations

- **WHEN** an admin principal requests a conversation list or detail route
- **THEN** the request succeeds with the existing conversation response contract

### Requirement: Dashboard sessions are bound to verified credentials

Every password or guest dashboard session MUST carry a fingerprint of the credential value actually verified when the session was issued. All cookie consumers, including session status, password management, trusted-header password fallback, and TOTP setup/verification, MUST reject a fingerprint that no longer matches the applicable stored credential. Legacy cookies lacking a credential fingerprint MUST require a fresh login. Changing or removing an administrator password MUST invalidate its earlier sessions; changing a guest password MUST invalidate earlier guest sessions without invalidating administrator sessions. Unrelated settings changes MUST NOT invalidate sessions.

A concurrent credential rotation between verification and cookie issuance MUST NOT give the earlier login a fingerprint for the new credential. TOTP verification MUST retain the original password credential fingerprint and absolute expiry, and MUST bind TOTP-verified state to the secret actually verified. Resetting the TOTP secret MUST invalidate verification of an earlier secret. Cross-replica recognition MAY take the existing settings-cache invalidation interval; the system MUST NOT claim immediate cluster-wide revocation. Logout SHALL continue to remove the client cookie without claiming per-cookie server-side revocation.

#### Scenario: Password rotation invalidates every cookie consumer

- **WHEN** the administrator password changes
- **THEN** an earlier cookie cannot access protected dashboard data, password management, or TOTP setup/verification
- **AND** session status does not advertise that cookie as password authenticated
- **AND** a fresh login with the new password succeeds

#### Scenario: Login races with rotation

- **WHEN** a login verifies the old password and the password rotates before cookie issuance
- **THEN** the issued cookie remains bound to the old credential and is rejected against the new credential

#### Scenario: Guest and ordinary settings remain independent

- **WHEN** a guest password changes
- **THEN** old guest cookies are rejected and administrator cookies remain valid
- **AND** changing a non-authentication setting does not invalidate either valid credential-bound session

#### Scenario: TOTP upgrade preserves credential and expiry

- **WHEN** a password-authenticated session completes TOTP verification
- **THEN** the upgraded cookie preserves its password fingerprint and original expiry bound
- **AND** a later password or TOTP-secret rotation rejects the old upgraded cookie
### Requirement: Password hashing does not block the request event loop

Dashboard password hashing and verification MUST execute outside the asyncio event-loop thread. Password work MUST be bounded to at most two concurrent jobs per process, independently of the number of login callers. Existing login rate limits and password validation semantics MUST remain unchanged. Cancelling a caller before admission MUST NOT start its password job; cancelling an admitted caller MUST retain its permit until the worker completes and MUST propagate cancellation without changing credentials or issuing a session.

#### Scenario: Other requests progress during password work

- **WHEN** a dashboard password operation is computing a bcrypt hash or check
- **THEN** the same process can serve an independent health request before that computation completes

#### Scenario: Cancellation does not free a running worker's permit

- **WHEN** two password workers are active and their callers are cancelled
- **THEN** a third password worker cannot start until an active worker completes
- **AND** cancelled password setup or login operations do not continue to persistence or session issuance

### Requirement: Login forms handle rejected authentication without unhandled promises

Administrator and guest login forms MUST display the authentication store's existing failure message without producing an unhandled promise rejection. Rejected credentials MUST NOT grant authentication. The form MUST permit a retry with corrected credentials without reloading the page. API error status and authentication-store authorization semantics MUST remain unchanged.

#### Scenario: Administrator corrects a rejected password

- **WHEN** an administrator submits an incorrect password and then a correct password
- **THEN** the first rejection displays its existing error without an unhandled promise
- **AND** the retry succeeds and clears the error

#### Scenario: Guest corrects a rejected password

- **WHEN** a guest submits an incorrect password and then a correct password
- **THEN** the first rejection displays its existing error without an unhandled promise
- **AND** the retry succeeds with guest permissions and clears the error
