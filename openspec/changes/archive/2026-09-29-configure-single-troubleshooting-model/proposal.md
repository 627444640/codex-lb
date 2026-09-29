# Configure one troubleshooting model

## Why
The troubleshooting assistant needs to start with the administrator-requested `mercury2.5` model and retain exactly one model selection. A free-form list must not be saved as though it were a model identifier.

## What Changes
- Default new or previously unconfigured assistant settings to `mercury2.5` without changing a valid existing model selection.
- Require one non-empty model identifier in administrator saves, with matching browser, LB API and monitor API validation. Reject arrays, whitespace-separated names and list syntax.
- Saving another model replaces the one stored value. Chat and explicit connection tests use that current value; visitors cannot choose a model.
- Preserve the existing enabled flag, key handling and controlled deployment boundary. Previously blank stored model values remain readable as the new default.

## Impact
Extends status-page-management in the existing paired development workspaces. No production deployment, credential provisioning or real-model acceptance is implied by this change.
