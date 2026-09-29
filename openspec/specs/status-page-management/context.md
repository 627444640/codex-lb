# Status-page management context

The independent monitor continues to collect availability and deliver confirmed alert events even when the LB process is unhealthy. Operators administer it only through Codex LB Settings, using the existing dashboard administrator session. The public monitor has no administrator login or browser mutation route.

The optional connector is `<CODEX_LB_DATA_DIR>/status-monitor.json` (mode 0600):

```json
{
  "url": "http://127.0.0.1:2466",
  "token_file": "/absolute/private/monitor-state/control-token.txt"
}
```

The monitor creates the credential file inside its private state directory. Connection and credential files must not be published. The LB data directory needs no new business-schema migration. Absence of the connector means disconnected/default-off. Only literal loopback destinations are accepted; redirects are not followed. A response/authentication/transport problem becomes a sanitized dashboard error, not a session logout or leaked upstream response.

SMTP authorization codes are write-only. An omitted or blank replacement keeps the previous code, and reads expose only `passwordConfigured`. The monitor writes a new private secret file and atomically changes the configuration reference; the worker uses the new settings on subsequent cycles. SMTP remains off until explicitly enabled. Announcement times use ISO 8601 in dashboard/control APIs and epoch timestamps only inside monitor persistence. All displayed calendar days use Asia/Taipei.

Seven-day capacity is weighted by the inspected LB plan-capacity constants. Incomplete fresh weekly data or an unknown plan weight yields unknown; monthly-only accounts do not create fictional weekly quota. The public response omits account counts. Calendar availability is successful readiness probes / probes with known outcomes for each local date, with sample coverage in the tooltip. It does not claim a completed business request on an idle day or invent history before monitoring began.

Example: an administrator saves a maintenance draft in Settings. It remains private. Publishing it with a future start date makes it appear in the centered announcement strip only at that time; withdrawal hides it immediately. A guest cannot read the draft or SMTP settings.

The deployment record currently defers the LB v1.24.2 rollout. This integration is implemented in source, built into a wheel and exercised through an isolated LB/monitor pair; the separate public display can be updated without restarting production LB. Installing the wheel and connector into production requires the existing controlled deployment procedure and authorization for that rollout.

## Local v1.24.3 integration — 2026-09-29

The user authorized merging this LB integration together with the independent
`feat` HTTP/SSE optimization into `v1.24.3`. The status-page source commit is
`d9973baf`, the stream feature is `f353140e`, and both were merged without conflicts.
The code retains the existing administrator boundary, optional/default-off
connector and write-only SMTP credential behavior. No migration was added.

Combined unit, API, frontend and isolated browser evidence is recorded in
`openspec/changes/integrate-status-page-settings/verification.md`, with synthetic
Settings screenshots. The production LB rollout hold remains; a local source
merge is not installation or acceptance of the independent live monitor.

## Administrator-maintained troubleshooting guides

Guides use the same administrator session and private monitor channel as announcements. They are stored in the monitor database, with a stable public anchor, status, order, revision and timestamps. Editing requires the current revision. Soft deletion hides an entry immediately; restoring it produces a draft, so content is not accidentally republished. The seed import has a durable once-only marker and does not overwrite subsequent edits.

The public page renders structured text on the server, independently of `/api/status`; it does not expose a management API or credentials. Text is escaped, optional addresses accept HTTP(S) without embedded credentials, and deleted/private content is not included in the HTML. The monitor control API limits guide mutations to 64 KiB. Guides use no source-LB schema or production account data.

Guide administration and model assistance use a separate v1.24.3 worktree and monitor copy, with isolated preview ports 2472 (LB) and 2471 (monitor). The base already contains the committed status-settings integration and HTTP/SSE optimization. Production installation remains a separate controlled rollout; changing the monitor HTML template must be deployed together with its new backend renderer.

## Guide-grounded model assistance

The administrator explicitly selected the existing Codex LB and an administrator-supplied authorized key. The monitor owns the private `troubleshooting-assistant.json` configuration (0600), exposes only a configured flag in administrator reads, and uses `/v1/chat/completions` with streaming diffusion, without tools, redirects or environment proxies. The model must support structured output; the completed answer is additionally validated locally and citations are generated only from retrieved current published guide IDs. This follows the [Inception streaming contract](https://docs.inceptionlabs.ai/capabilities/streaming) and [structured-output contract](https://docs.inceptionlabs.ai/capabilities/structured-outputs).

The independent public page adds an inference-only POST endpoint, not administrative mutations. It uses bounded ephemeral question/history input and published-guide keyword/CJK-fragment retrieval. No matching evidence avoids a model call. Chat text is not stored. `assistant_usage` stores only a per-day model-call count; it includes explicit administrator tests and attempted calls that fail. Common credentials are redacted, but this is not a guarantee that every possible secret format can be detected.

The monitor uses a 50-second overall model-call timeout, a 4 MiB total stream budget, 256 KiB event ceiling and 64 KiB text snapshot ceiling and a validated 6,000-character answer bound. It asks for concise answers. Request count and concurrency controls are not token/cost accounting; the assistant requests `max_completion_tokens: 2048`, which the external Chat Completions source route preserves; the administrator must still configure an appropriate model/key budget. No real credential was copied or provisioned for development. Synthetic-model HTTP and browser tests do not establish real-model availability or answer quality; those remain an administrator configuration/acceptance step.

The selected troubleshooting model defaults to the official `mercury-2.5` identifier. There is exactly one `model` string in the private configuration, not a list: saving a different identifier replaces it, and both chat and the explicit test read the same current value. The form and both server boundaries reject multiple names or list syntax even when the assistant is disabled. A valid existing selection remains unchanged; an older empty stored selection is interpreted as the new default until the next administrator save. Keys and enable state are preserved. This default is a gateway identifier, not evidence that the configured gateway/key can already call that model; the explicit generation and answer-quality checks still apply.

## Diffusion stream lifecycle

The browser requests SSE using `stream: true` on the public chat POST. The monitor sends `stream: true` and `diffusing: true` to its configured Chat Completions gateway. Provider `delta.content` values are full snapshots, not append-only deltas. Only the provisional `answer` field is exposed as a replacement snapshot; citation IDs/JSON scaffolding are never shown as drafts. A valid `stop` and `[DONE]`, final answer/citation checks and current guide revisions are required for a completed event. Only completed answers enter history. A stop button/page close aborts the reader; cancellation closes the upstream and releases concurrency. Legacy callers that omit `stream` still receive one validated JSON answer.

The gateway's external-source path already preserves unknown provider parameters and raw SSE bytes; regression coverage now checks diffusion passthrough. Existing usage-limited source keys intentionally buffer streams until usage settlement. That policy is unchanged: it can delay all snapshots until the end, and operators must verify the chosen key/gateway path before claiming live diffusion. Do not disable quota protections or synthesize animation to conceal buffering. The new default is `mercury-2.5`; valid saved `mercury2.5` aliases remain as administrator choices until explicitly edited.

## Live Mercury diffusion compatibility

Live provider probes on 2026-09-29 found two behaviors that synthetic full-JSON
fixtures did not reproduce. Default `medium` reasoning consumed most of the
2048-token budget and ended a guide-shaped response with `finish_reason: length`
before an answer could be validated. The known Mercury 2 / 2.5 identifiers now
request `reasoning_effort: instant`; the token budget, saved provider/model/key,
request controls and final answer/citation validation remain unchanged. This
uses Inception's [documented reasoning profile](https://docs.inceptionlabs.ai/capabilities/reasoning-efforts).

Real intermediate snapshots explicitly carry
`diffusion_meta.diffusion_content: true`, and even the `answer` field name can
be noisy. For those non-terminal frames only, a surviving first-string-value
delimiter can identify provisional answer text without displaying its damaged
key or the known citation field. If the key delimiter is also corrupted, a
bounded scan of at most 32 quote starts can identify a surviving longer text
fragment: the answer is the only string value in the requested schema. Numeric
citation lists and short field names are excluded. Unidentifiable frames are
omitted. Final JSON
is always parsed and validated strictly; the relaxed draft extraction never
promotes a malformed answer to completion.

The provider can deliver multiple real snapshots within milliseconds. The
browser now awaits its snapshot callback, allowing a rendering frame and a
short 65 ms presentation before consuming the next event. A 100 ms fallback
prevents a suspended animation frame from stalling the stream, hidden tabs skip
pacing, and abort interrupts the wait. All displayed text comes from actual
received snapshots; no fake denoising text is generated. Providers can still
supply only one safely identifiable snapshot for a short answer. These changes
do not remove upstream or gateway buffering and do not replace live-provider
acceptance with an animation.

Failed streams log only the processing stage, exception type, normalized finish
reason, event count, text length and reasoning profile. Questions, history,
answer content, source identifiers and credentials are not logged.
