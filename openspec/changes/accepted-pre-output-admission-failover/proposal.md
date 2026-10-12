## Why

Production on v1.24.4 accepted a websocket turn (`response.created`) and then failed it with `server_error` or `server_is_overloaded` before any model output. The admission failover note required the turn to still be pre-created, so `admission_failover_retried` stayed 0 and the request never left the failing account.

## What Changes

- Treat an accepted, output-free admission failure as the one shared pre-output retry.
- When the turn still carries `previous_response_id` and cached history exists, resend the full history without that anchor and close the original upstream first.
- A client-supplied anchor with no cached history stays put and surfaces.
- Text, tool or function calls, and reasoning all count as output.
- Apply the same rule on the HTTP bridge and HTTP streaming paths.

## Capabilities

### Modified Capabilities

- `account-admission-breaker`: accepted pre-output admission failures share the one history failover.

## Impact

Direct websocket, HTTP responses bridge, and HTTP streaming. No version bump in this change. Release waits for a separate decision.
