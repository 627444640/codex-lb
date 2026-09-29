# Live diffusion verification — 2026-09-29

## Observed failure

The configured provider was direct Inception with `mercury-2.5`; the deployed
files matched the source. The public SSE route reproduced an empty draft and
`model_unavailable`. A guide-shaped provider comparison at the same 2048-token
budget used 1597 reasoning tokens with `medium` and ended with `length`, without
a visible answer. `instant` used zero reasoning tokens and completed.

Real frames contained `diffusion_meta.diffusion_content: true`. Their answer
field name, quotes and colon could still be noisy. Multiple snapshots could
arrive within milliseconds, so immediate synchronous DOM replacements also
prevented their presentation between frames.

## Checks

- Monitor Python suite: **66 passed**.
- Stream parser and DOM interaction suite: **12 passed**, including coalesced
  snapshots and completion, abort during a pending paint, noisy field names,
  noisy delimiters, duplicate provider stop markers, malformed final JSON and
  metadata-only failure logging.
- Changed Python Ruff checks, JavaScript syntax and whitespace checks: passed.
- The change and all 59 main OpenSpec specifications: strict validation passed.
- Four running monitor files were updated with rollback copies retained. The
  monitor was reloaded using graceful SIGTERM and its existing KeepAlive policy;
  the LB backend and HTTPS supervisor PIDs were unchanged. Saved settings and
  credential file digests were preserved.
- A live public-endpoint request using the saved Inception configuration was
  processed by the actual served page scripts in a jsdom environment with
  animation frames. It displayed **49, 232 and 470 characters** at **1646, 1732
  and 1816 ms**, including **two actual revisions**, then completed at **1960 ms**
  with one validated guide source and no provisional draft remaining.
- The served JavaScript matched the fixed source and used `Cache-Control:
  no-store`. The main gateway remained healthy at `1.24.3`.

These timings describe one live acceptance request, not a latency guarantee.
No model text, user history or credentials were saved in diagnostic artifacts;
only event timing, lengths, hashes and protocol metadata were retained.

The native desktop browser connection returned `cgWindowNotFound` and exposed
no connected browser provider, so native screenshot/visual acceptance was not
completed. Live-provider streaming and real-script DOM transitions were verified
separately from that unavailable check. No Git commit or push was performed.
