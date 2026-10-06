# Design

The page keeps a single `role="progressbar"` element with `aria-valuemin`,
`aria-valuemax`, `aria-valuenow` and `aria-valuetext`. JavaScript creates 24
presentational spans on every render; `Math.round(clamped_percent / 100 * 24)`
determines the filled count. Unknown capacity renders 24 empty, muted blocks
and the accessible text `待核对` without inventing a percentage.

CSS uses a responsive grid with fixed gaps and short rounded blocks. The grid
shrinks with the card width and preserves the existing mobile layout. No API,
database, quota or incident behavior changes.
