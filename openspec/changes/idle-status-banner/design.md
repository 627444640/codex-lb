# Design

`collector.collect` already distinguishes idle traffic (`requests.total == 0`)
from degraded request quality and leaves the request component `unknown`; the
alert path also intentionally ignores that unknown state. The page-level
status reducer will use the same fact and omit only that idle request component
from its severity scan. Unknown or failed source/quota/gateway components still
keep the page unknown or unhealthy.

The browser receives the existing `requests` object and derives an `idle`
presentation flag from `total == 0`. The operational banner changes its title
and description only for that case. The request component label becomes “无样本”
and its detail states that business quality waits for a real request. No new
public schema field or persistence column is needed.
