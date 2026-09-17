## ADDED Requirements

### Requirement: Image request accounting uses public image usage
Image request logs and successful API-key settlements MUST use the image tool usage and effective image model. They MUST NOT reuse host Responses token counts. Log model, usage, and cost correction MUST be atomic and serialized with rollup folding. Missing modality evidence required for image pricing MUST produce an unknown cost.

#### Scenario: Host and image tool usage differ
- **WHEN** a host response reports different tokens from its image tool result
- **THEN** the image request log and successful settlement use the image tool tokens

#### Scenario: Image usage lacks modality details
- **WHEN** image usage omits details required to distinguish text from image pricing
- **THEN** the log retains reported totals and does not assign a fabricated cost
