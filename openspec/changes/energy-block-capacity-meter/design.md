# Design

The page keeps a single `role="progressbar"` element with `aria-valuemin`,
`aria-valuemax`, `aria-valuenow` and `aria-valuetext`. JavaScript creates 40
presentational spans on every render; `Math.round(clamped_percent / 100 * 40)`
determines the filled count. Filled blocks use green for values at or above
60%, yellow for values from 20% through below 60%, and red below 20%.
Unknown capacity renders 40 empty, muted blocks
and the accessible text `待核对` without inventing a percentage.

CSS uses a responsive grid with fixed gaps and short rounded blocks. The grid
shrinks with the card width and preserves the existing mobile layout. No API,
database, quota or incident behavior changes.
