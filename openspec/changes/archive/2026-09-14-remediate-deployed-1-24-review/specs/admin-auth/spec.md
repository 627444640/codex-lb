## ADDED Requirements

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
