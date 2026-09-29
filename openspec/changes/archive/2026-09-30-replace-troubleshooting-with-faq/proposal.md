## Why

The maintainer wants the independent troubleshooting page renamed to Frequently Asked Questions and the optional chat/LLM feature removed completely. Existing published guides and their administrator workflow must remain usable.

## What Changes

- Rename the public page, navigation and guide-management labels to FAQ / 常见问题; serve `/static/faq.html` and redirect the old page address.
- Retire the public chat, inference code, stream assets, assistant settings section, configuration/test APIs and schemas.
- Preserve guide content, revisions, deletion recovery, published anchors, status monitoring, email and announcements.
- Archive retired implementation and the private saved assistant configuration outside active runtime paths; ignore legacy assistant state without dropping historical tables or revoking an upstream key.
- Follow the maintainer's standing workflow: start a fresh `fix/` branch for each requested change, verify it, and merge it back into the branch from which the change started.

## Impact

- Dashboard settings and the optional status-monitor component only. Core Codex LB model routing and provider features are outside this removal.
- Former assistant APIs become unavailable and cannot trigger inference, including from stale clients.
- Preserve a private rollback copy, publish explicit refs to the maintainer's repository, then perform an idle, verified deployment/restart.
