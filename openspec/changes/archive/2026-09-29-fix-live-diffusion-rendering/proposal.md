## Why

The deployed troubleshooting assistant requests streaming diffusion, but Mercury's default reasoning can exhaust the bounded completion budget before a usable answer. Real diffusion events also arrive together within milliseconds; the browser currently replaces every snapshot and commits the final answer in one rendering turn, hiding the intermediate revisions.

## What Changes

- Use Mercury's documented instant reasoning mode for the recognized Mercury 2 / 2.5 model identifiers while preserving the answer schema and output budget.
- Await presentation of actual received snapshots so coalesced SSE frames can paint before the validated final answer replaces them.
- Extract the first answer string from explicitly marked, provisional diffusion frames when its field name is still being denoised; omit frames whose value boundary cannot be identified and keep terminal JSON parsing strict.
- Keep cancellation responsive, skip display pacing in hidden tabs, and never fabricate diffusion text or relax final-answer/source validation.

## Impact

- Independent troubleshooting monitor request construction and browser stream rendering only.
- Saved model, API key, destination, rate limits, daily limits and LB gateway behavior remain governed by the existing contracts.
- Verify using synthetic coalesced-frame regressions and bounded live probes of the configured provider, then update the running monitor under its existing service boundary.
