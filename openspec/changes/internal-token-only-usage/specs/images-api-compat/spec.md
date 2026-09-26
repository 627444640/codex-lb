## MODIFIED Requirements

### Requirement: Image request accounting uses public image usage

Image request logs and successful API-key settlement MUST use image-tool token usage and the effective image model rather than host Responses token counts. Model and usage correction MUST remain atomic and serialized with rollup folding. Every new image request MUST have null monetary cost and pricing version. Text/image modality evidence MUST NOT cause a price lookup or currency calculation.

#### Scenario: Host and image-tool usage differ

- **WHEN** a host response reports different tokens from its image-tool result
- **THEN** the image request log and successful settlement use image-tool tokens
- **AND** monetary fields remain null

#### Scenario: Image usage lacks modality details

- **WHEN** image usage reports totals without a text/image modality partition
- **THEN** those reported totals remain available
- **AND** no partition or monetary estimate is invented
