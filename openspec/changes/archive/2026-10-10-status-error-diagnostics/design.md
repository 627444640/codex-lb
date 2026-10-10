# Design

The collector will run one additional read-only aggregate query over the last
24 hours using the same normal-request filters already used for the live
15-minute request view: non-null account, non-empty model, `request_kind='normal'`
when available, no external model source, and case-insensitive Luna exclusion.
Soft-deleted rows are excluded when the source schema exposes `deleted_at`. The
query groups terminal outcomes by `error_code` and records only counts, latest
timestamp and model names. A small pure mapper converts known codes to stable
public categories and FAQ slugs. Unknown codes use an `other` category without
returning their raw code or message.

The public response adds `request_quality` alongside the existing `requests`
object. It contains `window_seconds`, `window_started_at`, `window_ended_at`,
`total`, `successes`, `cancelled`, `errors`, `error_percent`,
`last_error_at`, and `categories`. The existing `requests` object remains the
current-window contract so existing clients keep working.

The store's public serializer derives an `incident_summary` from the retained
public incident rows. It does not mutate or merge stored incidents. The summary
reports the number of request incidents opened in the recent 24-hour view and
counts all still-open request incidents, including incidents opened earlier.

The browser renders a new “近期请求质量” panel after the live request card.
The panel always states its window and sample boundary. Category rows use text
and percentage only, and the page shows a clear “当前窗口无请求，以下为最近 24
小时” state when the live card is idle. The readiness heading becomes
“基础探测正常率” and its note explicitly excludes model requests.

All timestamps remain epoch numbers inside the monitor's existing private/public
JSON convention and are rendered in Asia/Taipei by the existing formatter.
No migration or new runtime setting is needed.
