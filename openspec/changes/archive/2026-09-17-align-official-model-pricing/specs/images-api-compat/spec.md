## MODIFIED Requirements

### Requirement: Image request accounting uses public image usage
Image request logs and successful API-key settlements MUST use the image tool usage and effective image model. They MUST NOT reuse host Responses token counts. Log model, usage, and cost correction MUST be atomic and serialized with rollup folding. Missing modality evidence required for image pricing MUST produce an unknown cost. GPT-Image-2.5 Sunburst and Flare MUST use USD-per-million rates of 5/1.25 for text input/cache, 8/2 for image input/cache, and 30 for image output. ChatGPT-Image-Latest MUST use 5/1.25 for text input/cache, 8/2 for image input/cache, 10 for text output and 32 for image output.

#### Scenario: Host and image tool usage differ
- **WHEN** a host response reports different tokens from its image tool result
- **THEN** the image request log and successful settlement use the image tool tokens

#### Scenario: Image usage lacks modality details
- **WHEN** image usage omits details required to distinguish text from image pricing
- **THEN** the log retains reported totals and does not assign a fabricated cost

#### Scenario: Published image variants retain their modality rates
- **WHEN** usage is recorded for Sunburst, Flare or ChatGPT-Image-Latest
- **THEN** its cost uses the specified text/image rates and does not inherit an unverified family-prefix price
