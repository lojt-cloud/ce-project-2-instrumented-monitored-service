# Dashboard guide

This is a practical guide to reading `AuthServiceDashboard` in the moment, not why it's built the way it is, see MONITORING.md for that.

## Quick triage

Start with the top row. Four numbers, request rate, error rate, P95 latency, CPU utilization, designed to answer whether anything is wrong before looking at any trend line.

If something looks off, drill into the matching time series below it to see when it started and whether it's still happening. Login outcomes and Latency sit next to each other for this purpose, so a spike in one can be checked against the other without switching views.

Once the dashboard has pointed at what's wrong and roughly when, move to CloudWatch Logs Insights, filtering by correlation ID or username.
The dashboard tells you something is wrong and when, the logs tell you exactly what.

## What normal looks like, widget by widget

Request rate: a low, steady number matching whatever traffic is actually expected. A sudden jump usually means either a load test or an attack script running.

Error rate %: near zero under normal conditions. A rise means failed or blocked login attempts are increasing relative to successful ones.

P95 latency: sits close to the service's natural floor, roughly 300ms, most of that is `bcrypt`'s deliberately expensive password check. Note that this app runs a single Gunicorn worker, so a burst of concurrent legitimate traffic can also push this number up with nothing actually broken, check the Request rate panel for a concurrency spike before assuming a problem.

CPU utilization: low on a single small instance under light load.

Login outcomes: success (green) should dominate. Watch for failed (orange) climbing, blocked (red) appearing, and new lockouts (black) ticking up, that progression is the specific signature described below.

Latency, P50 vs P95: both should track closely together. A growing gap, P50 staying low while P95 climbs, means a subset of requests are having a meaningfully worse experience than everyone else, not the whole service degrading uniformly.

Saturation: flat and low across CPU, memory, and disk under normal conditions. A rise across all three together points to resource pressure, a rise in just one is more specific and worth checking against what changed.

## The brute-force signature

The pattern to watch for: the orange (failed) line in Login outcomes climbing, followed shortly by the black (new lockouts) line ticking up. The lockout is the strongest signal on this dashboard, it only fires once a specific account has crossed the app's own failure threshold, so it's close to unambiguous evidence of an attack rather than something that still needs interpreting.