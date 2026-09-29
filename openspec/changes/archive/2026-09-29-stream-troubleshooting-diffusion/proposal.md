# Stream troubleshooting diffusion snapshots

## Why
The administrator requested Mercury's real streaming diffusion output on the troubleshooting chat. The existing assistant buffers a Responses JSON result and cannot show revisions as they arrive.

## What Changes
- Request Chat Completions with `stream: true`, `diffusing: true` and the existing answer/citation JSON schema through the administrator's configured gateway.
- Parse bounded SSE frames across network/UTF-8 boundaries and replace provisional answer snapshots. Only a valid stopped, terminated stream with current citations becomes a completed answer.
- Stream snapshot/completed/error events to the browser, replace rather than append drafts, and support cancellation without committing drafts to follow-up history.
- Use the official new default `mercury-2.5`, retain valid saved aliases and the single-model administrator contract.
- Preserve existing gateway quota/accounting behavior. Usage-limited source keys may buffer upstream streams; do not disable that policy to obtain an animation.

## Impact
Paired development workspaces and delivery artifacts only. Validate gateway passthrough and incremental delivery with a clearly synthetic provider. Real Mercury authorization, output behavior and production deployment remain separately verifiable.
