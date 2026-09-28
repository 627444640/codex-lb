# Internal stream observation optimization

The user requested an independent `feat` branch, with later integration alongside
status-page settings into `v1.24.3`. The common base is `v1.24.2` (79ae33af).
This branch does not include the uncommitted status-page work, change release
metadata, merge v1.24.3, or deploy the running service.

Example: reasoning at 125 ms, empty text at 200 ms, real text at 250 ms and another
real text at 750 ms must still record TTFT=125, first output=250 and output count=2.
The empty frame must never make a one-chunk sample eligible under the existing
100 ms/two-chunk rule. Forwarded bytes, settlement order and terminal anchors stay
unchanged.

For later integration, create the release branch from the internal baseline,
merge the verified `feat` and status-page work separately, then rerun combined
proxy, settings/auth and browser checks. The status page owns Settings/API files;
this optimization owns proxy timing files. No database head is added here.
