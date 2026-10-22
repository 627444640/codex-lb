## 1. Authorized dependency update

- [x] 1.1 Verify the reviewed advisory, non-yanked patched PyPI release and exact failing image package; record the independent authorization and no-deployment boundary in issue #38 and context.
- [x] 1.2 Raise only the certifi floor and regenerate its locked release/artifacts; verify the diff contains no unrelated package-version change or private index URL.

## 2. Validation

- [x] 2.1 Check lock/manifest consistency and compare certifi artifact hashes with official PyPI metadata; verify the remaining package inventory is unchanged.
- [x] 2.2 Install only the patched certifi into a disposable environment and verify its CA bundle loads with hostname/certificate verification enabled and the affected root absent.
- [x] 2.3 Run strict OpenSpec maintenance validation and relevant static/packaging checks; record actual outcomes without claiming production installation or live upstream testing.

## 3. Publication and CI

- [ ] 3.1 Audit the candidate paths/history for privacy and publish a separate Draft PR linked to #38, based on the combined baseline validation candidate.
- [ ] 3.2 Inspect exact-head CI and the high-severity Trivy gate; record remaining failures honestly. Keep all PRs unmerged and do not deploy.
