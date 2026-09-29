# Administrator-managed troubleshooting guides

## Why
The public troubleshooting page currently requires editing HTML source. Administrators need to create, find, edit, order and remove entries through the existing Codex LB Settings identity.

## What Changes
- Add structured troubleshooting content to the monitor's independent SQLite store, with a one-time import of the two existing guides.
- Add authenticated Settings CRUD, publication, recoverable deletion and optimistic revision checks through the existing private monitor connection.
- Render only published entries in the existing independent public page; retain its URL, navigation, native disclosure controls and copy support.
- Keep production unchanged while verifying the feature in isolated copies and synthetic databases.

## Impact
Affected capability: status-page-management. Affected code: monitor content persistence/rendering/control, LB status-page schemas/service/routes and the Settings UI. No source LB business database migration, mail change, public credential or second administrator login.
