## MODIFIED Requirements

### Requirement: Mounted public FAQ loads its presentation assets

The public FAQ at `/status/static/faq.html` MUST load its stylesheet, theme,
font and script assets from the same `/status/static/` mount. It MUST remain
compatible with the standalone `/static/faq.html` address. The page MUST NOT
depend on an HTML `<base>` element when the response policy disables base URLs.

#### Scenario: Public FAQ renders with styles

- **WHEN** a browser opens `/status/static/faq.html`
- **THEN** the FAQ stylesheet, theme stylesheet, fonts and FAQ script resolve
  below `/status/static/`
- **AND** the page uses the styled monitor layout

#### Scenario: Standalone FAQ remains compatible

- **WHEN** a browser opens `/static/faq.html` on the monitor root
- **THEN** the same assets resolve below `/static/`
