# Design

The render function computes one `energyClass` from the known percentage:
`healthy` for values at or above 60%, `warning` from 20% through below 60%,
`critical` below 20%, and `unknown` when the value is absent or stale. It
assigns that class to both `#weekly-energy` and `#weekly-percent`. CSS maps the
same semantic classes to the existing success, warning, destructive and muted
theme colors.
