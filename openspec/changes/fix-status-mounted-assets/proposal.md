# Fix mounted status page assets

## Why

The public FAQ HTML was reachable, but its stylesheets and fonts were not
loaded in browsers. The status monitor response policy deliberately sets
`base-uri 'none'`, so the previous `<base>` element was ignored and relative
links resolved to a duplicated `/status/static/static/` path.

## What Changes

- Remove the ignored `<base>` elements from the monitor pages.
- Use path-relative FAQ resources and navigation that work at both `/static/`
  and `/status/static/`.
- Use relative font URLs in the monitor stylesheet.
- Update the managed runtime assets and verify browser-visible styling.
