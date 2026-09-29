# Verification — 2026-09-29

- Isolated monitor suite: 50 passed, including legacy empty values, replacement persistence, invalid-save atomicity, selected-model dispatch and visitor override rejection.
- LB API/service suites: 26 passed (`test_troubleshooting_assistant_settings.py`, `test_status_page_service.py`). Invalid model values are rejected before the private control service is called.
- Settings component suite: 8 passed, including default display, replacement payload, disabled-state validation and multiline paste rejection.
- TypeScript, targeted ESLint and Ruff checks passed. Vite production build passed using the existing Node installation; no dependency installation was needed.
- Change validation and all 59 main specifications passed strict validation.
- Real HTTP preview bridge (2472 → 2471): default Mercury value, replacement, invalid input rejection and readback passed. The preview is saved with `mercury2.5`, disabled and with no configured model key. The checks did not call a model or increase daily usage.

Existing synthetic model tests confirm the selected value reaches both chat and explicit generation-test requests. Mercury 2.5 authorization, the exact gateway alias and real structured-output/answer quality are not verified by these tests. No production rollout or new browser visual acceptance is claimed.

The paired wheel and monitor v2 ZIP were rebuilt. Wheel schema/frontend files and all ZIP members match the working sources. Both delivery patches pass read-only `git apply --check` against their current canonical source directories. Artifact hashes are recorded in the private development delivery manifest; neither patch was applied to production.
