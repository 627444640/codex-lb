## ADDED Requirements

### Requirement: APIs tab shows token usage without monetary charts

The APIs tab MUST show available token usage and request metrics for the selected key without a cost donut or monetary totals. Retained `accountCosts` and cost-trend API fields MUST NOT activate a monetary display. The token trend MUST use the available panel width and retain its accumulated toggle.

#### Scenario: Historical monetary data does not restore the donut

- **GIVEN** the selected key has historical account costs and token trend data
- **WHEN** the detail panel renders
- **THEN** its chart shows only the token trend
- **AND** no account-cost panel, cost axis or currency legend is displayed

#### Scenario: Monetary history alone does not create an empty chart

- **WHEN** the selected key has historical cost data but no token trend points
- **THEN** the dashboard does not create a chart from monetary data

### Requirement: APIs tab token trend controls remain accessible

The APIs token trend MUST retain its heading, token-only description, token legend and accessible accumulated switch. It MUST render a single token series and token axis. Historical cost points MUST NOT affect chart values, axes or date selection.

#### Scenario: Token trend preserves accumulation

- **WHEN** the operator enables the accumulated switch
- **THEN** the visible token series becomes cumulative
- **AND** no cost series or currency axis is added

### Requirement: Request logs expose token evidence with legacy response compatibility

The request-log API MUST preserve available input, output, cached-read, cache-write and reasoning token fields. It MAY retain old cost response keys for compatibility, but MUST NOT calculate a monetary breakdown. A stored historical cost MAY appear as a historical total; absent monetary segments MUST be null. Missing token evidence MUST remain null rather than being invented.

#### Scenario: Request log exposes token evidence

- **WHEN** a request log has input, cached-input and output usage
- **THEN** its API representation exposes that token evidence
- **AND** a new row has no monetary estimate

#### Scenario: Reasoning fallback remains compatible

- **WHEN** a historical row lacks output tokens but has reasoning tokens
- **THEN** the existing output-token fallback remains available without generating a price

#### Scenario: Legacy partial data remains valid

- **WHEN** a log is missing optional token or monetary fields
- **THEN** its compatible response shape remains valid with null unavailable values

### Requirement: Request detail dialog renders token usage without billing

Request details MUST retain available token counts, timing and request metadata without a monetary total or cost breakdown section. Partial or failed rows MUST remain inspectable according to existing availability rules.

#### Scenario: Historical cost is not shown in details

- **GIVEN** a successful row carries a historical monetary total
- **WHEN** the administrator opens its detail dialog
- **THEN** available token evidence remains visible
- **AND** no cost section or currency amount is rendered

### Requirement: Reports distribution donuts show compact request totals

Both model and User-Agent distribution cards MUST show request counts and request-based percentages. Their centers MUST display `Total` and a compact request count with up to two fractional digits and K/M/B suffixes. The cards MUST NOT expose a currency metric or selector. Legends MUST retain hover-linked slices, four visible rows and accessible scrolling for additional rows.

#### Scenario: Legacy costs do not affect distribution

- **GIVEN** distribution rows contain request counts and old monetary values
- **WHEN** a distribution card renders
- **THEN** its slices, totals, percentages and legends derive only from requests
- **AND** hover linkage and scrolling remain available

### Requirement: Reports distribution donuts show request totals

Both model and User-Agent distribution cards MUST show request counts and request-based percentages. Their centers MUST display `Total` and a compact request count with up to two fractional digits and K/M/B suffixes. The cards MUST NOT expose a currency metric or selector. Legends MUST retain hover-linked slices, four visible rows and accessible scrolling for additional rows.

#### Scenario: Legacy costs do not affect distribution

- **GIVEN** distribution rows contain request counts and old monetary values
- **WHEN** a distribution card renders
- **THEN** its slices, totals, percentages and legends derive only from requests
- **AND** hover linkage and scrolling remain available

### Requirement: Dashboard summary omits monetary cards

The dashboard MUST NOT render an estimated API cost card or per-hour/per-day monetary averages. It MUST retain request, token, cache, conversation and error metrics supported by the existing overview.

#### Scenario: Stored amounts do not restore a cost card

- **GIVEN** a compatible overview payload contains a historical cost total
- **WHEN** the overview renders
- **THEN** its operational metrics remain visible without a monetary card

### Requirement: Reports distribution cards use request metrics

The two report distribution cards MUST use request counts without a monetary toggle. They MUST preserve independent hover highlighting and MUST NOT render hover tooltips.

#### Scenario: Request counts define both distributions

- **WHEN** an operator views model and User-Agent distributions
- **THEN** both cards show request counts and independently highlight their active legend rows
- **AND** no cost selector or currency value appears

## MODIFIED Requirements

### Requirement: Request logs distinguish actual and requested service tiers
When a request log entry includes service-tier data, the dashboard request-log API response MUST expose the effective compatibility tier, requested tier, and actual tier separately. The recent-requests UI MUST display the actual tier when available and MUST show the requested tier when it differs from the visible actual tier.

#### Scenario: Dashboard shows upstream-selected tier and requested tier
- **WHEN** a request log entry is recorded with `requested_service_tier: "priority"`, `actual_service_tier: "default"`, and effective `service_tier: "default"`
- **THEN** the `GET /api/request-logs` response includes `requestedServiceTier: "priority"`, `actualServiceTier: "default"`, and `serviceTier: "default"`
- **AND** the dashboard renders the model label with `default`
- **AND** the dashboard also shows that the request asked for `priority`

### Requirement: Reports page renders English user-facing labels

The dashboard SHALL render `/reports` with the following exact page-owned user-facing labels for the current reports surface:

- `Usage Report`
- `Usage history by date range`
- `Loading...`
- `Tokens`
- `Requests`
- `Tokens by Day`
- `Distribution by Model`
- `Distribution by UserAgent`
- `Daily Breakdown`
- `Day`
- `Input Tokens`
- `Output Tokens`
- `Accounts`
- `Total`
- `Failed to load report data:`
- `Failed to load model and user-agent options:`
- `Failed to load account options:`
- `Some report data could not be loaded. Try reloading.`
- `Retry`

Backend-provided strings, account values, model values, and raw server error payload text SHALL remain out of scope for this wording change unless `/reports` renders page-owned labels around them.

#### Scenario: Reports page shows English labels

- **WHEN** an authenticated operator opens `/reports`
- **THEN** the page title is `Usage Report`
- **AND** the subtitle is `Usage history by date range`
- **AND** the summary cards include `Tokens` and `Requests`
- **AND** the chart and table section titles include `Tokens by Day`, `Distribution by Model`, `Distribution by UserAgent`, and `Daily Breakdown`
- **AND** the daily table headings include `Day`, `Input Tokens`, `Output Tokens`, and `Accounts`

#### Scenario: Reports page state labels are English

- **WHEN** `/reports` renders a loading, empty, or error state
- **THEN** the loading label is `Loading...`
- **AND** page-owned error wrappers use `Failed to load report data:`, `Failed to load model and user-agent options:`, and `Failed to load account options:` when those failures render
- **AND** the retry warning is `Some report data could not be loaded. Try reloading.`
- **AND** the retry button label is `Retry`

### Requirement: Reports exposes a persisted line-chart visibility filter

The `/reports` page MUST expose a visible multi-select immediately before the
date controls. Its options MUST use the localized existing chart-header keys
`reports.charts.tokensByDay`,
`reports.charts.timeToFirstToken`, `reports.charts.tokensPerSecond`, and
`reports.charts.queueWait`. The multi-select filter label MUST use the
`reports.filters.charts` key, and that key MUST be provided in each of
`en.json`, `ko.json`, and `zh-CN.json`. All four options MUST be selected by
default.
Selected line-chart cards MUST render, deselected line-chart cards MUST NOT
render, and an empty selection MUST be valid. Summary, donut, and table
sections MUST remain visible regardless of line-chart selection.

#### Scenario: Reports selects all line charts by default

- **WHEN** the `/reports` page loads without a saved visibility preference
- **THEN** the multi-select has all four chart options selected
- **AND** all four line-chart cards render
- **AND** the summary, donut, and table sections remain visible

#### Scenario: Reports renders a partial selection

- **GIVEN** the operator selects only Tokens by Day and Queue Wait
- **WHEN** the Reports page renders
- **THEN** only those two line-chart cards render
- **AND** the other two line-chart cards do not render
- **AND** the summary, donut, and table sections remain visible

#### Scenario: Reports permits an empty selection

- **GIVEN** the operator deselects all four chart options
- **WHEN** the Reports page renders
- **THEN** no line-chart cards render
- **AND** the summary, donut, and table sections remain visible

#### Scenario: Reports provides the chart filter label in every required locale

- **WHEN** the frontend locale resources are checked
- **THEN** `en.json` provides a `reports.filters.charts` label
- **AND** `ko.json` provides a `reports.filters.charts` label
- **AND** `zh-CN.json` provides a `reports.filters.charts` label

### Requirement: Reports safely persists visibility

Reports MUST store the selected chart IDs as a JSON array under the exact
localStorage key `codex-lb-reports-visible-charts`. The only known chart IDs
MUST be the following four, in this canonical order: `tokensByDay`, `timeToFirstToken`, `tokensPerSecond`, `queueWait`. This
canonical order MUST be used for normalization, persistence, and rendering.
Missing storage MUST default to all four known chart IDs. A valid array MUST
be filtered to known IDs, deduplicated, and normalized to canonical chart
order; an empty array MUST remain empty. Malformed JSON, non-array values,
arrays containing any non-string values, and localStorage access failures MUST
default to all four known chart IDs. Storage failures MUST NOT disable
current-session in-memory visibility changes.

#### Scenario: Reports restores a persisted subset

- **GIVEN** localStorage contains a valid JSON array with the IDs for Tokens by
  Day and Queue Wait
- **WHEN** the `/reports` page initializes
- **THEN** those two chart options are selected
- **AND** their line-chart cards render
- **AND** the other two line-chart cards do not render

#### Scenario: Reports ignores unknown IDs and normalizes persisted values

- **GIVEN** localStorage contains a valid JSON array with known IDs in a
  non-canonical order, duplicate known IDs, and unknown IDs
- **WHEN** the `/reports` page initializes
- **THEN** unknown IDs, including retired `costByDay`, are ignored
- **AND** duplicate IDs occur only once
- **AND** the selected IDs are normalized to canonical chart order

### Requirement: API key overview SHALL show lifetime usage aggregates

The key overview MUST present request and token totals using lifetime non-warmup `usageSummary` data unless a bounded backend window is explicitly provided. It MUST NOT show monetary totals. Request and token distributions MUST reflect those respective metrics.

#### Scenario: Overview scope remains lifetime

- **WHEN** the overview renders key-list usage summaries
- **THEN** its request and token totals retain their lifetime scope
- **AND** charts show requests by key and lifetime tokens by key without a monetary chart

### Requirement: Dashboard overview summary cards show previous-window usage deltas

The dashboard overview API SHALL expose previous-window comparison data for the existing `Requests` and `Tokens` summary cards returned by `GET /api/dashboard/overview`. The comparison SHALL be tied to the selected overview timeframe so that `1d` compares the current 1-day window with the immediately preceding 1-day window, `7d` compares the current 7-day window with the immediately preceding 7-day window, and `30d` compares the current 30-day window with the immediately preceding 30-day window.

The overview response SHALL include a comparison block that exposes whether previous-window comparison is allowed and the previous-window totals for requests and tokens. The dashboard SHALL use that block to render a compact percentage-change indicator on the existing `Requests` and `Tokens` cards only. The dashboard MUST NOT add this indicator to `Error rate` or `Account burn projection`.

If the immediately preceding window is not fully covered by eligible request-log history for the selected timeframe, the overview response SHALL mark the comparison as unavailable and the dashboard SHALL hide the percentage-change indicator for those cards.

If previous-window comparison is available and the previous total for a card is greater than zero, the dashboard SHALL calculate the displayed change from the current total relative to the previous total, SHALL show increases with an upward indicator using the project's positive `emerald` styling, and SHALL show decreases with a downward indicator using the project's negative `red` styling.

#### Scenario: Daily overview renders increase from previous window

- **WHEN** `GET /api/dashboard/overview?timeframe=1d` returns current totals for requests and tokens plus comparison data with `canCompare: true`
- **AND** the previous-window totals are lower than the current-window totals
- **THEN** the dashboard renders percentage-change indicators on the `Requests` and `Tokens` cards
- **AND** each increase uses an upward indicator with positive `emerald` styling

#### Scenario: Weekly overview renders decrease from previous window

- **WHEN** `GET /api/dashboard/overview?timeframe=7d` returns comparison data with `canCompare: true`
- **AND** at least one of the previous-window totals for requests or tokens is higher than the current-window total for that same card
- **THEN** the dashboard renders a downward percentage-change indicator for that card
- **AND** that decrease uses negative `red` styling

#### Scenario: Partial previous window suppresses comparison

- **WHEN** `GET /api/dashboard/overview?timeframe=7d` or `GET /api/dashboard/overview?timeframe=30d` cannot prove the immediately preceding same-length window is fully covered by eligible request-log history
- **THEN** the overview response marks the comparison as unavailable
- **AND** the dashboard does not render percentage-change indicators on the `Requests` or `Tokens` cards

#### Scenario: Non-comparison cards remain unchanged

- **WHEN** the dashboard renders overview cards from `GET /api/dashboard/overview` with or without comparison data
- **THEN** `Error rate` and `Account burn projection` do not render previous-window percentage-change indicators

### Requirement: Reports user-agent distribution preserves unknown buckets without collisions

`GET /api/reports` SHALL aggregate request-log rows whose normalized `request_logs.useragent_group` is `null` into a `byUseragent` bucket labeled `Missing User-Agent`. Real normalized `request_logs.useragent_group = "Unknown"` rows SHALL remain in a separate `Unknown` bucket. When `/reports` or `GET /api/reports` is filtered with `useragent_group=Missing User-Agent`, the system SHALL match those same null-backed rows, while `useragent_group=Unknown` SHALL match only real `"Unknown"` rows. The `/reports` `Distribution by UserAgent` card SHALL render the `Missing User-Agent` bucket with a fixed gray legend marker and slice color instead of a rotated palette color.

#### Scenario: Reports payload includes missing and real Unknown user-agent traffic

- **WHEN** `GET /api/reports` aggregates request logs that include one or more rows with `request_logs.useragent_group = null`
- **AND** one or more rows with normalized `request_logs.useragent_group = "Unknown"`
- **THEN** the response `byUseragent` array includes an entry with `useragent: "Missing User-Agent"`
- **AND** that entry aggregates only the null-backed rows' request counts
- **AND** the response separately includes an entry with `useragent: "Unknown"` for the real normalized `"Unknown"` rows

#### Scenario: Reports filters distinguish missing and real Unknown user-agent traffic

- **WHEN** `/reports` or `GET /api/reports` requests `useragent_group=Missing User-Agent`
- **THEN** the returned report aggregates include only rows whose normalized `request_logs.useragent_group` is `null`
- **WHEN** `/reports` or `GET /api/reports` requests `useragent_group=Unknown`
- **THEN** the returned report aggregates include only rows whose normalized `request_logs.useragent_group` is the real string `"Unknown"`

#### Scenario: Reports page renders the missing user-agent bucket with fixed gray styling

- **WHEN** `/reports` renders `Distribution by UserAgent` data that includes `useragent: "Missing User-Agent"`
- **THEN** the `Missing User-Agent` legend dot uses a fixed gray color
- **AND** the matching donut slice uses that same fixed gray color

### Requirement: Reports daily charts fill missing selected days with zero-value rows

The dashboard SHALL render `/reports` `Tokens by Day` charts from a continuous daily series covering every selected day from the current `startDate` through `endDate`. When `GET /api/reports` omits a selected date, the page SHALL insert a zero-value daily row for that date before rendering the token chart.

#### Scenario: Missing API dates render as zero-value chart points

- **WHEN** an authenticated operator views `/reports` for a selected date range and the `daily` response omits one or more selected dates
- **THEN** the `Tokens by Day` chart includes a point for every selected day from `startDate` through `endDate`
- **AND** each omitted date renders with zero token counts
- **AND** the `Tokens by Day` chart includes a point for every selected day from `startDate` through `endDate`
- **AND** each omitted date renders with `inputTokens = 0`, `outputTokens = 0`, `cachedInputTokens = 0`, `requests = 0`, `activeAccounts = 0`, and `errorCount = 0`

### Requirement: Daily Breakdown supports explicit visible-column sorting

The dashboard SHALL render `/reports` `Daily Breakdown` with sortable visible columns for `Day`, `Reqs`, `Input Tokens`, `Output Tokens`, and `Accounts`. The default sort SHALL be `Day` descending.

#### Scenario: Daily Breakdown defaults to newest day first

- **WHEN** an authenticated operator opens `/reports`
- **THEN** the `Daily Breakdown` rows are ordered by `Day` descending by default

#### Scenario: Daily Breakdown toggles sorting for a visible column

- **WHEN** an authenticated operator activates any `Daily Breakdown` visible-column header
- **THEN** the table sorts by that column
- **AND** activating the same header again toggles the sort direction between ascending and descending

### Requirement: Dashboard request details expose client IP

The administrator request-log API response MUST expose the persisted `clientIp` value when present, and the request-log table MUST include its IP column by default. Guest responses and IP search MUST retain sensitive-field redaction. The Request Details dialog MUST render `Client IP` with the full value when present, MUST allow copying the value, and MUST render `—` when no client IP is stored.

#### Scenario: Request details show client IP

- **WHEN** a request log entry has `clientIp: "203.0.113.7"`
- **THEN** the Request Details dialog renders `Client IP` with value `203.0.113.7`
- **AND** the value can be copied

#### Scenario: Request details show missing client IP

- **WHEN** a request log entry has `clientIp: null`
- **THEN** the Request Details dialog renders `Client IP` with value `—`

### Requirement: Conversation filter state is removable and summarized

When a conversation filter is active, the dashboard MUST render a removable
conversation badge between the Statuses control and Reset. Dismissing the badge
MUST clear only the conversation filter and reset pagination. When the filtered
API response includes conversation metadata, the dashboard MUST render a
summary box between the filter row and request-log table with the form:

`The conversation ${id} runs ${count} request(s)`. The ID and count MUST be separate styled inline-code values without literal backticks.

If at least one other non-conversation filter is active, the summary MUST append
an inline suffix describing those active filters and MUST omit the conversation
filter from that suffix. If no other non-conversation filter is active, the
summary MUST omit the suffix. The response-level `conversation` metadata MUST
contain only `requestCount` and `aggregatedCostUsd`; it MUST NOT duplicate the
conversation ID because the active URL-backed filter already identifies it.

#### Scenario: Dismissing the badge clears only conversation state

- **GIVEN** the conversation badge and other request-log filters are active
- **WHEN** the badge is dismissed
- **THEN** only the conversation filter is cleared
- **AND** pagination resets
- **AND** the other filters remain active

#### Scenario: Summary describes the active filtered conversation

- **GIVEN** the active URL-backed conversation filter is `conv-a` and the
  filtered response contains
  `conversation: { requestCount: 12, aggregatedCostUsd: 1.23 }`, with timeframe
  and status filters also active
- **WHEN** the request-log page renders
- **THEN** the summary appears between the filter row and table
- **AND** it states the active conversation ID and request count without currency
- **AND** its inline suffix describes the timeframe and status without repeating
  the conversation filter
- **AND** the response-level conversation metadata contains exactly
  `requestCount` and `aggregatedCostUsd`, with no ID field

#### Scenario: Summary omits suffix without other filters

- **GIVEN** the active URL-backed conversation filter is `conv-a` and no other
  non-conversation filter is active
- **WHEN** the request-log page renders
- **THEN** the summary contains the conversation sentence without an inline
  filter suffix

### Requirement: Dashboard and report metrics count distinct conversations

Dashboard overview metrics MUST include a Conversations card alongside Tokens and Error Rate, counting distinct non-empty conversation IDs in the
selected timeframe. Report summary metrics MUST include a Conversations card
immediately after Requests, counting distinct non-empty IDs across the complete
filtered report range. A conversation spanning multiple days MUST count once in
each applicable daily row and once in the report-wide total. Neither card MUST
render a `{count} distinct` secondary label.

#### Scenario: Dashboard count deduplicates IDs

- **GIVEN** the selected dashboard timeframe contains repeated, null, and empty
  conversation IDs
- **WHEN** overview metrics are rendered
- **THEN** the Conversations card counts each distinct non-empty ID once
- **AND** the card is alongside Tokens and Error Rate

#### Scenario: Report summary and daily counts use distinct IDs

- **GIVEN** one conversation has requests on two report days and another has
  requests on one day
- **WHEN** report metrics are rendered
- **THEN** the summary counts two distinct conversations overall
- **AND** each applicable daily row counts the spanning conversation once
- **AND** the Conversations summary card is immediately after Requests

### Requirement: Reports summary cards show previous-window deltas conservatively

`GET /api/reports` SHALL expose a `comparison` block for the `Tokens` and `Requests` summary cards that includes `canCompare` plus the previous-window totals for tokens and requests. The current window and previous window SHALL use equal calendar-window lengths derived from the selected report date range. The endpoint SHALL set `canCompare` to `true` only when eligible report history fully covers the immediately preceding window. When `canCompare` is `false`, the `/reports` summary cards SHALL hide the previous-window percentage indicators. Even when `canCompare` is `true`, an individual summary card SHALL hide its own percentage indicator when that card's previous-window total is zero.

#### Scenario: Reports summary cards show previous-window increase

- **WHEN** `GET /api/reports` returns current summary totals plus `comparison.canCompare: true`
- **AND** a previous-window total for `Tokens` or `Requests` is lower than the current total for that same card
- **THEN** the matching summary card renders a visible percentage-change increase indicator

#### Scenario: Incomplete previous window suppresses comparison

- **WHEN** the earliest eligible report activity is later than the start of the immediately preceding report window
- **THEN** `GET /api/reports` returns `comparison.canCompare: false`
- **AND** the `/reports` summary cards do not render previous-window percentage indicators

#### Scenario: Zero previous total suppresses the matching card indicator

- **WHEN** `GET /api/reports` returns `comparison.canCompare: true`
- **AND** the previous-window total for one of `Tokens` or `Requests` is `0`
- **THEN** that summary card does not render a previous-window percentage indicator
- **AND** the other summary cards may still render percentage indicators when their own previous-window totals are greater than `0`

### Requirement: Reports daily breakdown renders a continuous calendar window

The `/reports` daily breakdown table SHALL render one row per calendar day in the selected date range. Each row SHALL display its date as an ISO `yyyy-mm-dd` calendar date string. If the reports API omits one or more days inside that range, the table SHALL synthesize zero-valued rows for those days using the same row styling as API-backed rows. The table SHALL keep the header visible while only the data rows scroll, with a default visible body height of seven row heights.

#### Scenario: Daily breakdown fills missing days with zero-valued rows

- **WHEN** the selected reports window spans `2026-06-05` through `2026-06-12`
- **AND** the reports API returns daily rows for every day except `2026-06-06`
- **THEN** the daily breakdown renders a row for `2026-06-06`
- **AND** that row shows zero requests, zero input tokens, zero output tokens and zero accounts
- **AND** that row uses the same row styling as neighboring rows

#### Scenario: Daily breakdown header stays visible while rows scroll

- **WHEN** the daily breakdown contains more than seven rows
- **THEN** the table header remains visible
- **AND** only the table body scrolls vertically through the remaining rows

#### Scenario: Daily breakdown preserves ISO bucket dates

- **WHEN** the reports API returns a daily bucket row with `date` set to `2026-06-01`
- **THEN** the daily breakdown table renders that row label as `2026-06-01`

### Requirement: Reports daily charts use symmetric horizontal padding

The `/reports` `Tokens by Day` charts SHALL use equal left and right horizontal plot padding within their chart cards.

#### Scenario: Daily charts render with balanced left and right inset

- **WHEN** an authenticated operator opens `/reports`
- **THEN** the `Tokens by Day` charts render with equal left and right horizontal padding around the plotted area

### Requirement: Dashboard numeric units stay locale-independent

Dashboard quantities that use compact formatting SHALL use `K`, `M`, and `B`
suffixes regardless of the selected interface locale so requests, tokens,
balances, pool totals, projections, and configured thresholds remain directly
comparable. Dashboard USD values SHALL use the `$` prefix across locales.

#### Scenario: Simplified Chinese compact quantity display

- **WHEN** a user selects `zh-CN`
- **AND** views compact request, token, or credit quantities
- **THEN** 10,200 renders as `10.2K`
- **AND** 1,500,000 renders as `1.5M`
- **AND** 1,500,000,000 renders as `1.5B`

### Requirement: Reports per-day averages use the inclusive local calendar window

`GET /api/reports` MUST calculate `summary.avgRequestsPerDay` and any retained historical-only
`summary.avgCostPerDay` compatibility value by dividing the respective stored report totals by exactly
`(end_date - start_date).days + 1`. The divisor MUST represent the selected
inclusive local calendar-date window and MUST NOT be derived from the
UTC-converted filter boundaries.

#### Scenario: Offset-to-zero transition keeps a two-day divisor

- **WHEN** an operator requests `2026-02-15` through `2026-02-16` in
  `Africa/Casablanca` and the report totals are 60 cost units and 30 requests
- **THEN** `avgCostPerDay` is `30`
- **AND** `avgRequestsPerDay` is `15`

#### Scenario: Offset-from-zero transition keeps a two-day divisor

- **WHEN** an operator requests `2026-03-22` through `2026-03-23` in
  `Africa/Casablanca` and the report totals are 60 cost units and 30 requests
- **THEN** `avgCostPerDay` is `30`
- **AND** `avgRequestsPerDay` is `15`

### Requirement: Dashboard conversation listing

The authenticated dashboard MUST expose `GET /api/conversations`. The list
endpoint MUST accept `limit`, `offset`, `search`, `since`, and `timeframe` query
parameters. The server-authoritative `timeframe` parameter MUST accept `1d`,
`7d`, or `30d`; when it is supplied, the server MUST derive the activity window
from the shared dashboard timeframe configuration and the client MUST NOT
substitute a browser-clock-generated `since` value. `timeframe` and `since` MUST
not be supplied together. When `since` is omitted, the server MUST apply a
rolling 30-day lower bound;
explicitly older `since` values MUST be capped at that same bound, and incoming
timezone-aware datetimes MUST be normalized to naive UTC before querying. It
MUST aggregate eligible `request_logs` rows by the raw, non-empty
`conversation_id` column, excluding rows whose request kind is `warmup` or
`limit_warmup`, and rows with `deleted_at IS NOT NULL`. Production request-log
writes MUST normalize ASCII padding and blank conversation IDs before storage;
conversation list, facet, and detail queries MUST use raw-column
`conversation_id` predicates and grouping rather than function-wrapped
expressions.

Search MUST be case-insensitive and match the normalized conversation ID or any
eligible row's user-agent family. Search MUST select whole conversations first:
after a conversation matches, aggregation MUST include all eligible rows in that
conversation, including rows whose user-agent family or ID did not match the
search text. The endpoint MUST derive aggregates from `request_logs` only.

When `since` is provided, a conversation MUST be selected when at least one
eligible row has `requested_at >= since`. A conversation MAY have eligible rows
before `since` and MUST still be included when it has activity in the window.
The grouped summary MUST aggregate all eligible rows for every selected
conversation, so `firstRequest`, `lastRequest`, `requestCount`, token totals,
cached-token totals and any retained historical monetary totals MUST NOT be clipped to the window. Membership MUST
be implemented as an in-window aggregate condition and MUST NOT use a global
pre-window ID set or a pre-window anti-join.

After page membership is selected, the account, API-key, and model facet
queries for the returned page MUST use the same full eligible-row scope as the
summary, restricted only by the selected page's raw `conversation_id` values.
The facet queries MUST NOT add a `requested_at >= since` restriction after
membership selection; facet representatives and remaining counts MUST include
eligible history before `since` and MUST remain consistent with the full-history
summary aggregates.

The response MUST contain `conversations`, `total`, and `hasMore` pagination
fields. Each row in `conversations` MUST contain exactly these fields and no
response summary object:

- `conversationId`: the normalized, non-empty conversation identity.
- `firstRequest`: the earliest `requested_at` among all eligible rows in the
  conversation.
- `lastRequest`: the latest `requested_at` among all eligible rows in the
  conversation.
- `requestCount`: the number of eligible rows in the conversation.
- `representativeAccount` and `remainingAccountCount`.
- `apiKeyId` and `apiKeyName`.
- `representativeModel` and `remainingModelCount`.
- `totalTokens`.
- `cachedInputTokens`.
- `totalCostUsd`.

The camelCase names above are the external Dashboard API JSON contract. Python
schema, service, and repository identifiers MAY remain snake_case internally;
internal names MUST NOT be emitted as alternate response fields.

`totalTokens` MUST equal total input tokens plus total output tokens, with
`reasoning_tokens` used for a row when `output_tokens` is null.
`cachedInputTokens` MUST use the existing per-row clamp: null remains null;
otherwise the cached value is clamped to `[0, input_tokens]` when input tokens
are present. At aggregate level, null per-row values MUST NOT be converted to
zero; when every eligible row has a null cached value, `cachedInputTokens` MUST
be null, and otherwise it MUST equal the sum of the known clamped values.

Representative account values MUST use `request_count DESC,
latest_requested_at DESC, lexical account ASC`. List model values MUST be
grouped by distinct model, combining all reasoning efforts for that model, and
the representative model MUST use `request_count DESC, latest_requested_at DESC,
model lexical ASC`. Null account values MUST be excluded from account
candidates; if no non-null account exists, `representativeAccount` MUST be null
and `remainingAccountCount` MUST be 0. The list MUST NOT split model values by
`reasoning_effort`; `(model, reasoning_effort)` grouping MUST be used only for
conversation details.

Nullable and multiple-key conversations MUST be handled deterministically. Null
API-key values MUST not be candidates; if no non-null key exists, both API-key
fields MUST be null. When multiple distinct non-null keys exist, `apiKeyId` MUST be selected by
`request_count DESC, latest_requested_at DESC, lexical API-key ID ASC`, and
`apiKeyName` MUST be the corresponding existing dashboard-safe display name.
`apiKeyName` MUST never expose a secret, hash, or plaintext key material.

The list order MUST be stable: `lastRequest DESC`, then normalized
`conversationId ASC`. Pagination MUST be applied after this ordering.

#### Scenario: Pagination uses the stable list order

- **GIVEN** matching conversations have different latest request times and a
  tie exists on `lastRequest`
- **WHEN** the client calls `GET /api/conversations?limit=10&offset=20`
- **THEN** rows are ordered by `lastRequest DESC` and ties by normalized
  `conversationId ASC`
- **AND** the response starts at the 21st row in that order and reports the
  matching total and whether another page exists

#### Scenario: Blank IDs, warmups, and soft-deleted rows are excluded

- **GIVEN** request logs include null IDs, whitespace-only IDs, `warmup` rows,
  `limit_warmup` rows, soft-deleted rows, and eligible rows with non-empty IDs
- **WHEN** the client calls `GET /api/conversations`
- **THEN** only rows whose request kind is neither `warmup` nor `limit_warmup`,
  which are non-soft-deleted and have non-empty normalized IDs, contribute to
  returned conversations

#### Scenario: Search selects whole conversations

- **GIVEN** one eligible conversation contains a matching user-agent family on
  one row and non-matching user-agent/ID values on other rows
- **WHEN** the client calls `GET /api/conversations?search=opencode`
- **THEN** that conversation is selected
- **AND** all eligible rows in that conversation contribute to its counts,
  tokens and cached tokens, with historical monetary fields retained only for API compatibility
- **AND** rows from conversations with no matching ID or user-agent family are
  not returned

#### Scenario: List search is case-insensitive over normalized IDs and user-agent families

- **GIVEN** an eligible conversation has a normalized ID and user-agent family
  whose letters differ in case from the search text
- **WHEN** the client calls `GET /api/conversations?search=OPENCODE`
- **THEN** the conversation is selected when either the normalized ID or any
  eligible row's user-agent family matches case-insensitively

#### Scenario: Since filter selects conversations active in the window

- **GIVEN** conversation `conv-old` has its earliest eligible row at `t-10d`
  and a later row at `t-1d`, and conversation `conv-new` has its earliest
  eligible row at `t-1d`
- **WHEN** the client calls `GET /api/conversations?since=<t-7d ISO>`
- **THEN** both `conv-new` and `conv-old` are returned
- **AND** `conv-old` is included because it has a row inside the window even
  though its first message predates the window
- **AND** both conversations' summaries aggregate every eligible row, not only
  rows at or after `since`

#### Scenario: Since membership and facets share the full conversation scope

- **GIVEN** a selected conversation has eligible account, API-key, and model
  values both before and after the `since` boundary
- **WHEN** the client calls `GET /api/conversations?since=<ISO>`
- **THEN** `firstRequest`, `lastRequest`, `requestCount`, and summary totals
  include all eligible rows for the conversation
- **AND** account, API-key, and model facet counts and representatives include
  all eligible rows in the selected conversation, including rows before `since`

#### Scenario: Since filter composes with search and pagination

- **GIVEN** two conversations have activity inside the `since` window and only
  one matches the search text
- **WHEN** the client calls `GET /api/conversations?since=<ISO>&search=opencode`
- **THEN** only the matching conversation is returned
- **AND** the response total and hasMore reflect the since-and-search filtered
  set

#### Scenario: List model representatives ignore reasoning effort

- **GIVEN** a conversation has requests for the same model with multiple
  reasoning-effort values and requests for another model
- **WHEN** the client calls `GET /api/conversations`
- **THEN** the list groups the same model's requests into one model value
- **AND** the representative model is ordered by request count descending,
  latest request descending, and model lexical ascending
- **AND** the remaining model count counts distinct models, not model/effort
  combinations

#### Scenario: API-key representation is safe and deterministic

- **GIVEN** a conversation has null API-key rows and multiple non-null API-key
  values with tied counts
- **WHEN** the client calls `GET /api/conversations`
- **THEN** null values do not become the representative
- **AND** the non-null representative is selected by count, latest request, and
  lexical API-key ID
- **AND** the response contains only the corresponding dashboard-safe name and
  never secret, hash, or plaintext key material

### Requirement: Dashboard conversation view

The dashboard MUST render Request Logs by default. The original uppercase
section-title typography MUST be retained, and the title itself MUST be the
single accessible Radix-style selector trigger with `ChevronDown` for Request
Logs and Conversations. A separate selector MUST NOT render to the title's
right. Selecting Conversations MUST persist `view=conversations` in the URL;
selecting Request Logs MUST return to the existing request-log view.

The dashboard MUST retain separate URL-backed query state for Request Logs and
Conversations, including each view's applicable filters and pagination.
Switching views MUST NOT reinterpret, overwrite, or clear the inactive view's
query state, and returning to a view MUST restore its retained state.

The Conversations view MUST NOT render a free-text filter input above the list.
The view MUST render a day-range selector with exactly three options — `1d`,
`7d`, and `30d` — placed at the top-right of the dashboard page alongside the
refresh action and shown only while the Conversations view is active. The
selector MUST default to `7d`. The selected value MUST be persisted in the URL
as `conversationTimeframe`, MUST drive the list endpoint's `timeframe` query
parameter using the same symbolic key (the server derives the effective window),
and MUST NOT generate a browser-clock-derived `since` parameter. It MUST reset
pagination to offset 0 on change. The selector's values and default
MUST mirror the dashboard overview timeframe selector, with no unbounded
"all" option. The view MUST use the list endpoint's
established loading, error, empty, and pagination behavior.
While Conversations is active, the dashboard overview query that supplies the
statistics cards MUST use the active `conversationTimeframe`, including on the
initial render when that value is restored from the URL. The independently
retained `overviewTimeframe` MUST continue to drive the overview query when
Request Logs is active.

The conversation list MUST render exactly these columns in order: Last request,
Conversation, Accounts, API key, Models, Tokens, and Details. Last request
MUST use the request-log Time column's two-line time/date presentation. Accounts
MUST resolve the representative account ID through the dashboard account
summaries and display `displayName`, then email, then the ID as a final fallback.
Accounts and models MUST render remaining values as a smaller muted `+ N more`
secondary line. Tokens MUST show total tokens with cached input tokens on a
subordinate line.
When dashboard privacy blur is enabled, an account label resolved from an email
fallback MUST render with the established `privacy-blur` class; display-name
and account-ID fallback labels MUST remain unblurred.
The API-key column MUST use `apiKeyName` only. Details MUST use the existing
Details button treatment.

The details dialog MUST render row one as conversation ID, start, and latest;
row two as account count, total elapsed time, and dominant user-agent family;
and a model/effort table with exactly these displayed columns, in order: Model
(effort), Reqs, Total elapsed, Total input (with total cache as a
subordinate/parenthetical value), Total output. Total cache MUST
not be a separate displayed column. The table MUST default to Reqs descending
and MUST support client-side sorting for every displayed column without adding a
sort query parameter.
The displayed conversation ID MUST NOT provide a copy action.

The detail dialog MUST use the established dashboard loading state while the
detail API is pending. Unknown or malformed conversation IDs, including a
standard detail API 404, MUST use the standard dashboard error display and retry
behavior. Nullable optional aggregate values MUST render the established
em-dash or other dashboard fallback value without breaking the row or dialog.
An empty conversation list MUST render the established dashboard empty state.
When an empty conversation list is returned for a nonzero pagination offset, the
Conversations view MUST retain its pagination controls so the operator can
navigate back to the first or previous page. The initial empty state at offset
zero MUST NOT render pagination controls.

#### Scenario: Request Logs is the default and selector switches views

- **WHEN** an operator opens the dashboard
- **THEN** Request Logs is visible and active by default
- **WHEN** the operator selects Conversations
- **THEN** the Conversations list renders and the URL contains
  `view=conversations`

#### Scenario: Request Logs and Conversations retain independent URL query state

- **GIVEN** Request Logs has active filters and pagination and Conversations has
  different active filters and pagination retained in the URL
- **WHEN** the operator switches between the two views
- **THEN** each view restores its own filters and pagination
- **AND** switching views does not reinterpret, overwrite, or clear the other
  view's query state

#### Scenario: Conversations has no free-text filter and renders the day selector

- **WHEN** the operator opens the Conversations view
- **THEN** no free-text filter input is rendered above the list
- **AND** a day-range selector with exactly `1d`, `7d`, and `30d` options is
  rendered at the top-right of the dashboard page alongside the refresh action
- **AND** the selector defaults to `7d` and no unbounded "all" option is offered
- **AND** the list renders the specified reordered columns and two-line request
  time presentation
- **AND** representative account IDs resolve to display name, then email, then ID
- **AND** smaller muted `+ N more` account/model secondary lines and cached
  tokens as a subordinate line are rendered

#### Scenario: Conversation day selector persists in the URL and drives timeframe

- **WHEN** the operator changes the Conversations day selector from `7d` to `30d`
- **THEN** the URL gains `conversationTimeframe=30d` (or drops the param when the
  default `7d` is selected)
- **AND** the list endpoint is called with `timeframe=30d`
- **AND** the list endpoint does not receive a browser-clock-derived `since`
- **AND** pagination resets to offset 0

#### Scenario: Conversation timeframe drives active dashboard statistics

- **GIVEN** the URL restores `conversationTimeframe=30d` while
  `overviewTimeframe` is absent or has a different value
- **WHEN** the operator opens the Conversations view
- **THEN** the statistics-card overview query uses the `30d` timeframe
- **AND** the conversation list uses `timeframe=30d`
- **AND** the independently retained overview timeframe remains unchanged
  for the Request Logs view

#### Scenario: Conversation day selector state is independent per view

- **GIVEN** the Conversations day selector is set to `30d`
- **WHEN** the operator switches to Request Logs and back to Conversations
- **THEN** the Conversations view restores its retained `30d` selector state
- **AND** the Request Logs view state is unaffected

#### Scenario: Conversation account privacy blur applies only to email fallback

- **GIVEN** dashboard privacy blur is enabled and account labels resolve using
  display name, email fallback, and account-ID fallback values
- **WHEN** the Conversations list renders
- **THEN** only the email-fallback label has the established `privacy-blur` class
- **AND** the display-name and account-ID fallback labels remain unblurred

#### Scenario: The original-styled title is the only view selector

- **WHEN** the list section renders
- **THEN** its uppercase title typography is retained
- **AND** activating the title opens the Request Logs/Conversations selector
- **AND** no separate selector is rendered to the title's right

#### Scenario: Conversation details use established loading and retry states

- **WHEN** the detail API is loading for a selected conversation
- **THEN** the dialog uses the established dashboard loading state
- **WHEN** the detail API returns an unknown or malformed-ID error
- **THEN** the dialog uses the standard dashboard error display with retry

#### Scenario: Nullable detail aggregates use dashboard fallbacks

- **GIVEN** a successful detail response contains nullable optional aggregate
  values
- **WHEN** the operator opens the details dialog
- **THEN** each nullable value renders the established em-dash or dashboard
  fallback without breaking the row or dialog

#### Scenario: Empty conversation results use the existing empty state

- **GIVEN** the conversation list response contains no rows
- **WHEN** the operator opens the Conversations view
- **THEN** the existing dashboard empty state is rendered

#### Scenario: Empty later conversation pages retain pagination controls

- **GIVEN** the operator is on a nonzero Conversations page and the list
  response contains no rows
- **WHEN** the Conversations view renders the response
- **THEN** the existing dashboard empty state is rendered
- **AND** pagination controls remain visible
- **AND** the first-page and previous-page controls provide a path back to
  earlier results

#### Scenario: Details dialog has the approved layout and sorting

- **WHEN** the operator opens a conversation's Details dialog
- **THEN** row one contains conversation ID/start/latest
- **AND** conversation ID has no copy action
- **AND** row two contains account count/total elapsed/dominant user-agent
- **AND** the table displays exactly Model (effort), Reqs, Total elapsed, Total
  input (with total cache as a subordinate/parenthetical value), Total output
- **AND** the table initially sorts by Reqs descending
- **AND** activating any displayed table column header reorders only the returned
  rows client-side

### Requirement: Conversation list renders metrics and readable duration

The dashboard SHALL render columns in this order: Last request, Lasted,
Conversation, Accounts, API key, Models, Requests, Tokens, Details.
The Lasted value SHALL use `lastRequest - firstRequest`, displaying `0s` for
zero duration, seconds for durations under one minute, `xm ys` for durations
under one hour, `xh ym` for durations under one day, and `xd yh` for durations
of at least one day. The conversation-ID cell SHALL be top-aligned.

#### Scenario: Duration uses two units and preserves zero

- **WHEN** a row spans 2 hours and 15 minutes
- **THEN** Lasted displays `2h 15m`
- **WHEN** a row spans 2 days and 3 hours
- **THEN** Lasted displays `2d 3h`
- **WHEN** firstRequest equals lastRequest
- **THEN** Lasted displays `0s`

## REMOVED Requirements

### Requirement: APIs tab shows a 7-day account-cost donut for selected API keys

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: APIs tab account-cost donut uses existing account labels and privacy rules

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: APIs tab account-cost donut follows the dashboard donut visual system

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: APIs tab usage trend control layout is compact in the split view

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Request logs expose cost breakdown details

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Request detail dialog renders successful cost breakdowns

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Reports distribution donuts show compact active-metric totals

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Reports distribution donuts show active-metric totals

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Dashboard estimated cost card meta avoids duplicate estimate and cache copy

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.

### Requirement: Reports distribution cards toggle between cost and requests

**Reason:** The internal distribution retires the corresponding anonymous-reporting or monetary behavior.

**Migration:** Preserve historical records and revisions. Apply the token-only and no-collector requirements; do not run a data cleanup or reactivate the removed UI or sender.
