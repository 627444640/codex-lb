# Knowledge-grounded troubleshooting assistant

## Why
Visitors should be able to paste an error into the troubleshooting page and receive an explanation and suggested steps grounded in the published guide database. Administrators chose to reuse their Codex LB through a configured model and authorized server-side API key.

## What Changes
- Add a chat panel above the guide list with Enter-to-send, Shift+Enter newline, bounded follow-up context and source links.
- Add administrator-only configuration for the existing LB /v1 base URL, model, write-only key, enable switch and request budgets, plus an explicit model-generation connection test.
- Retrieve only current published, non-deleted guides. No matching evidence produces a clarification response without a model call. Validate structured answers and server-generated citation links.
- Keep conversation text ephemeral, redact common credential patterns before sending, limit request sizes/concurrency/frequency/daily usage and never give the model database or system tools.
- Clarify that the independent page prohibits administrative browser mutations; its new inference POST endpoint does not grant content-management permission.

## Impact
Extends status-page-management and the isolated monitor/LB preview pair. The public POST endpoint performs inference only; administrative writes remain private. Production deployment is still separately controlled. No production key will be copied or auto-created.
