- [x] Update the fixed upstream frame and derived `response.create` constants
      to 65 MiB and 64 MiB.
- [x] Update code comments and OpenSpec references that describe the old
      16 MiB / 15 MiB boundary.
- [x] Add regression coverage for the default constants and derived transport
      budget.
- [x] Run focused unit tests and strict OpenSpec validation; the repository
      `.venv` needed a temporary test-only `jwt` import stub because PyJWT is
      not installed in the sandbox.
