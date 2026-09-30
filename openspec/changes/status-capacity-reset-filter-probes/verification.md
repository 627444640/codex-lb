# Verification

Validation and rollout completed on 2026-09-30 (Asia/Taipei):

- The monitor suite passed 42 tests. Ruff check/format and the status-page
  JavaScript syntax check also passed.
- The public response now returns `capacity.weekly_next_reset_at` alongside
  `weekly_remaining_percent`; the LAN status API returned a fresh non-null
  value after restart, and the overview HTML contains the reset display node.
- A live readback after restart showed only the non-Luna model in the normal
  request aggregate, zero current request errors, and an operational request
  component. The runtime monitor database event and incident counts remained
  unchanged, confirming that historical records were preserved and no new
  Luna event was created.
- The matching collector, store, HTML, JavaScript and CSS files were copied
  into the LaunchAgent runtime after a private before-snapshot. Source and
  runtime SHA-256 values matched for every installed file.

The repository `openspec` CLI is unavailable in the execution environment, so
strict CLI validation and archival remain unverified. Historical requests and
events were not rewritten; the Luna filter applies to subsequent snapshots.
