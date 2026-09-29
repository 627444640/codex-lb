## Why

The internal 1.24.3 development branch still carries 1.24.0 in every release-managed version field, so the dashboard correctly reads an outdated value. Operators also need the footer to identify this fork as an internal build.

## What Changes

- Synchronize the existing release-managed version fields to 1.24.3 using the shared release helper.
- Render the selected runtime/build version with a localized internal-build label, including `1.24.3内部版` in Chinese.
- Preserve runtime-version priority, the build-version fallback, and the existing update indicator.

## Impact

- Dashboard footer and synchronized package metadata only; no new configuration or API fields.
- Release-please's last-published manifest and CHANGELOG remain under the release workflow's ownership.
- Source and isolated preview verification do not install or restart the production service.
