# Design

## State model

The monitor keeps three independent signals:

1. `capacity.weekly_remaining_percent` is the weighted seven-day pool
   capacity. The existing 60%/20% visual thresholds remain presentation
   thresholds for this number only.
2. The public `quota` component is the routability signal. `operational`
   means at least one active account has a complete, fresh quota window;
   `unknown` means the monitor cannot determine eligibility; `outage` means
   there are no active accounts or every known active account is exhausted.
3. The public `quota_warning` component is advisory. It is `degraded` when a
   known lowest window is below `low_quota_percent` or an account is exhausted,
   but it is marked `advisory` so it cannot raise the page-level status,
   readiness history, incidents, or email alerts. Its copy says that some
   account reserve is low; it never says `额度不足`.

The quota component detail uses `额度不足` only for the routability outage
case. A low reserve with a ready account says `仍有可路由额度`.

## Privacy and operator detail

The public response continues to omit the internal pool object and all account
counters. It may expose the existing aggregate component states and the
weighted capacity percentage. The loopback-authenticated `/internal/settings`
response gains a sanitized `quota` object with stale state, aggregate
counters, lowest remaining percentage, threshold, and routability. It does
not include account IDs, plan rows, or raw source data.

The dashboard Settings status-page panel renders this private summary. Stale
data clears derived numeric values rather than presenting an old count as
current.

## Alert and readiness boundaries

Advisory components are excluded from the page-status reducer, daily readiness
calendar, alert debounce, incident creation, and email events. The routing
component remains part of those boundaries. Existing component IDs and public
capacity fields remain compatible; the advisory uses a new `quota_warning` ID.

## Compatibility and verification

No database migration is needed. Existing historical incidents remain intact.
Tests cover low reserve with routable accounts, exhausted-account failover,
true no-quota outage, unknown/stale data, public privacy, internal sanitized
detail, top-level status, alert exclusion, and DOM labels.
