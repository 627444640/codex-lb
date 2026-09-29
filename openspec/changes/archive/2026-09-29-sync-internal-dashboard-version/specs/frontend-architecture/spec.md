## ADDED Requirements

### Requirement: Internal fork footer version identity

The internal fork's dashboard footer SHALL render the running application's version with a localized internal-build label. It SHALL prefer `GET /api/runtime/version`'s `currentVersion` and use the frontend's build version while that value is unavailable. The footer SHALL derive the version number from those sources rather than embed a release number in its display code. The internal label SHALL be presentation-only and SHALL NOT change machine-readable versions or update comparisons.

#### Scenario: Current internal build in Chinese

- **WHEN** the runtime version is `1.24.3` and the dashboard language is Chinese
- **THEN** the footer displays `1.24.3内部版`

#### Scenario: Runtime version advances beyond the frontend build

- **WHEN** the runtime reports `1.24.4` and the frontend was built with `1.24.3`
- **THEN** the Chinese footer displays `1.24.4内部版`

#### Scenario: Runtime lookup fails

- **WHEN** the runtime version API is unavailable
- **THEN** the footer displays the frontend's build version with the localized internal-build label
- **AND** it does not show an update-available icon
