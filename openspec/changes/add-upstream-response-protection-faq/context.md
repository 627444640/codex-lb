# Context

The recent incident showed that the gateway can select an account and start a
stream successfully before the upstream response fails with
`internal_error` / `response protection is unavailable`. The available logs
prove the gateway's classification and the concentration on one sticky
account, but they do not retain the original upstream SSE frame. The FAQ must
therefore explain the observed boundary without claiming that a particular
upstream component, account credential, Cloudflare edge or local queue is the
confirmed root cause.

The guide should direct an operator to wait and retry once, compare a healthy
alternate account and model, and record a redacted timestamp/model/entry point
for escalation. It must not instruct users to submit API keys, full request
bodies or raw conversation screenshots. A seed marker increment is required:
the monitor imports seed rows only once, so the upgrade path must add the new
row to an existing monitor without overwriting administrator content.
