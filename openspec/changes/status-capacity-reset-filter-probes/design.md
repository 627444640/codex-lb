# Design

`pool_summary` already keeps a `next_reset_at` value for each fresh weekly
window. The public capacity helper will preserve its existing scalar return
for callers and add a details helper that returns the weighted percentage plus
the earliest applicable weekly reset. `Store.public` serializes that timestamp
as `capacity.weekly_next_reset_at`; a stale snapshot returns both capacity
values as unknown.

The request source query will add a case-insensitive model predicate that
excludes names containing `luna`. This is intentionally model-based because
the live probe rows can be persisted as `request_kind=normal` and do not carry
a stable probe-only marker. The predicate runs before grouping and timing
aggregation, so excluded probes cannot raise the `requests` component to
degraded/outage and cannot create a new request incident or email event.

No data migration or historical event rewrite is performed. Existing events
remain readable, while the next collector snapshot recomputes request health
from the filtered set and clears the old request alert state only through the
normal recovery debounce.
