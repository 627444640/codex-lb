# Add a problem-report link to the public status pages

## Why

Users need a direct way to report a new Codex LB problem after reading the
public FAQ. The report destination is a Lark Base form maintained separately
from the read-only status monitor.

## What Changes

- Add a `问题上报` link immediately after `常见问题` in the overview and FAQ
  navigation.
- Open the Lark form in a new tab with an explicit `noopener noreferrer`
  relation.
- Style the link as a compact highlighted navigation button while preserving
  the existing responsive header.

## Impact

The status monitor remains read-only and does not receive or persist report
submissions. The external form is the user-facing submission destination; the
public pages do not expose credentials, monitor control routes, or status
polling changes.
