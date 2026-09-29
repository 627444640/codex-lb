## ADDED Requirements

### Requirement: Troubleshooting assistant retains exactly one model
New assistant settings SHALL default to the exact model identifier `mercury2.5`. Administrator saves MUST contain a single non-empty model identifier of at most 120 characters, using letters, digits, periods, underscores, colons, slashes, at signs or hyphens and starting with a letter or digit. Both the LB and monitor APIs MUST reject model arrays, list syntax and multiple names in one string. A rejected save MUST leave the previous configuration unchanged. The administrator form SHALL explain that saving another model replaces the current selection. Public chat SHALL use only the current saved selection and MUST NOT allow a visitor-supplied model.

#### Scenario: New or previously unconfigured assistant
- **WHEN** settings do not exist or an older stored model is an empty string
- **THEN** the administrator reads `mercury2.5` as the model
- **AND** existing valid model identifiers, keys and enabled flags are preserved

#### Scenario: Administrator replaces the model
- **WHEN** an administrator saves a different valid model identifier
- **THEN** exactly that identifier replaces the previous one
- **AND** the next chat or explicit connection test uses the replacement without a model pool or fallback list

#### Scenario: Administrator submits more than one model
- **WHEN** the model is an array, a serialized list or multiple names separated by whitespace, commas or semicolons
- **THEN** the update fails validation even while the assistant is disabled
- **AND** the previous saved model and credentials remain unchanged
