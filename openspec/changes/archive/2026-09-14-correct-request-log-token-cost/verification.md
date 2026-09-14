# Verification

All traffic and browser examples used synthetic data. No live inference call,
production database mutation or service restart was performed.

- Complete backend unit suite: 6,416 passed, 71 skipped. Skips comprise 68
  Helm-dependent checks (Helm unavailable) and 3 existing obsolete lock-conflict
  scenarios; none is an accounting regression test.
- Complete frontend suite: 1,159 passed across 146 files. Subsequent narrow-column
  wrapping/default-width regression suite: 38 passed, followed by a successful
  rebuild and browser comparison.
- Final SQLite accounting/API/migration/capture/rollup slice: 81 passed.
- PostgreSQL upgrade, downgrade, re-upgrade and schema-drift check passed;
  accounting/API/capture/rollup slice: 78 passed before the final read-only
  provenance guard, which is additionally covered by the final SQLite slice.
- Proxy image/compact/warmup/API-key budget slice: 150 passed; Responses: 65 passed.
- Bridge/WebSocket slice: 766 passed initially; the two remaining cases passed
  separately after updating the new metadata mock and allowing local socket bind.
- Cancellation, settlement, transport metadata and architecture slice: 1,154 passed.
- Ruff, formatting, Ty, proxy architecture and git diff whitespace checks passed.
- All 57 main specifications passed normal validation; the change passed strict
  validation. Main-spec strict warnings about pre-existing purpose text are outside
  this change.
- Built dashboard accepted real backend responses in the isolated browser smoke
  test. Before/after synthetic request comparisons produced no browser page errors.
- Wheel and sdist built successfully. Wheel contents were byte-checked against
  the current changed application code, migration and dashboard entry point;
  runtime credential/config/database files were absent from both artifacts.

Independent review additionally found and fixed explicit unknown image costs
being reconstructed from flattened usage, current custom-source estimates being
misclassified as historical, and cache-write premiums missing from admission
reservations. Explicit unknown image estimates also remain unknown after a later
pricing-version change. Existing rollup watermarks and success-only quota
settlement policy are preserved.
