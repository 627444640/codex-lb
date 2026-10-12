## ADDED Requirements

### Requirement: The managed macOS proxy documents the public status mount

The maintained macOS Caddy example and operator documentation SHALL show the
`/status/` path proxy to the loopback monitor, the `/status` trailing-slash
redirect, and the proxy-level denial for `/status/internal/*`. The example
MUST continue to keep the monitor process on loopback and the existing
port-`2467` LAN site separate.
