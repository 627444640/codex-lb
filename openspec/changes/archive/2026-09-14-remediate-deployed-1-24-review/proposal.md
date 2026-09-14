## Why

The reviewed deployed 1.24.0 source has excessive decompression allocation, ineffective credit quotas, credential revocation gaps, tool-history identity loss, unbounded downstream queues, blocking password work, retained cache history, and a macOS RSS high-water-mark error.

## What Changes

Close R01/R04/R05/R06/R07/R08/R09/R11 at their shared boundaries, preserve quota units and tool identity, and handle rejected dashboard logins without unhandled promises. The private deployment fixes R02/R03/R10 remain outside this public checkout. This branch uses clean upstream v1.24.0 ancestry and contains no withdrawn deployment files or their history.

## Impact

HTTP ingress, dashboard authentication, API keys, Responses bridging, usage caching, and memory admission. Existing authentication/role/TOTP, billing settlement, and protocol behavior have focused and broad verification. No schema migration or production deployment is performed by this change.
