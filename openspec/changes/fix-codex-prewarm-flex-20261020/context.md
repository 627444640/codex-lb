# Scope and evidence

The incident window was 2026-10-20 09:11:48–10:11:48 Asia/Taipei. Twelve
no_plan_support_for_model results were request_kind=prewarm, requested tier
Flex. Both affected model catalogs advertised Priority but no Flex. The
endpoint regression first failed on the existing code with an error frame.

The fix uses the existing authoritative model_advertises_service_tier query
and runs before reservation, account selection and payload serialization.
It applies to any catalog-known model, without hard-coded model names. The
normalization event records the requested Flex value; effective request-log
tier fields follow the existing normalized-tier accounting contract.

This is a no-generation compatibility rule, not a generic tier downgrade.
Literal generate=false is mandatory on each frame; a connection marker does
not authorize rewriting later normal turns. Unknown catalogs fail unchanged.
No account is granted Flex, Priority or Ultrafast entitlement by this change.

Starting target: fix/previous-response-replay-loop-20261019 at a37cc13e.
Existing uncommitted work was left in the original checkout. Both changed
runtime files were byte-identical to installed e1b47a9c before this patch.

## Verification before deployment

The original endpoint regression produced no_plan_support_for_model before
upstream connection. The fix passes 342 tests across the prewarm policy,
request policy, model registry, load-balancer contracts and WebSocket endpoint
suite. The route regression verifies prewarm completion and a later normal
Priority frame on the same connection, plus unchanged normal Flex rejection
on a fresh connection. Established ordinary sockets continue forwarding tiers
under the existing contract. Ruff check, format check and diff check pass.
The change and all 61 main OpenSpec specifications passed strict validation.

Production delivery is a recorded two-file overlay on e1b47a9c / 1.24.9,
not a deployment of all newer source commits. Original runtime bytes, package
RECORD and deployment metadata are backed up before replacement. The base
release identity remains intact with separate overlay provenance.

The exact deployed wheel plus the two runtime changes also passed 20 selected
prewarm tests (158 deselected), with app imports verified from the staged
baseline rather than the newer source checkout. A read-only production catalog
check confirmed normalization only for generate=false on both incident models.
At 2026-10-20 11:22:18 +08:00, verified-TLS HTTPS/WebSocket probes against the
still-unpatched service returned no_plan_support_for_model for both models.
The probes used the existing client API key in memory and no-generation frames.

The fix commit is 13d445487ef6b1accbe21dadba152e8c01cd733d, merged locally as
f97455c979cec001f84de9e8ef22c1e8511e6367. Seven pre-existing modified files
were hash-verified unchanged around that merge. Two reversible 20-second drain
attempts were cancelled because active requests remained; neither attempt
changed installed files or stopped the backend.

A third reversible drain at 11:26:35 +08:00 reached zero bridge pending work
but retained one process in-flight request for the full observation window.
It was cancelled at 11:26:55 without restarting or changing installed files.
Production loading and post-deployment live validation remain pending until
active work ends. The OpenSpec change remains active and is not archived.
