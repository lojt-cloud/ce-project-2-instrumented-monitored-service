# Monitoring

## Dashboard

`AuthServiceDashboard`, deployed from `config/dashboard.json`. The file is a template, `${AWS_REGION}` and `${INSTANCE_ID}` get substituted with `envsubst` before it's applied with `aws cloudwatch put-dashboard`, so the same file works regardless of which instance or region it's pointed at.

## Golden Signals

Request rate: the "Request rate (5 min)" widget. There's no dedicated request-count metric, so this uses the `SampleCount` statistic on `api_latency_ms` instead, since that metric gets pushed exactly once per request regardless of outcome, its data point count is a direct proxy for request volume.

Errors: "Error rate %" and its time-series counterpart. Both are a metric math expression, `(login_failed_total + login_blocked_total) / (login_success_total + login_failed_total + login_blocked_total) * 100`, treating failed and blocked login attempts as the error signal for this service.

Latency: "P95 latency (ms)" and the "Latency" time series, which plots P50 against P95.

Saturation: "CPU utilization" and the "Saturation (CPU / memory / disk)" time series, both sourced from the CloudWatch agent's OS-level metrics.

## Widget reference

Top row, four single-value widgets for an at-a-glance status check: request rate, error rate, P95 latency, and CPU utilization.

Login outcomes: a time series of `login_success_total`, `login_failed_total`, `login_blocked_total`, and `account_lockouts_total`. Colored deliberately rather than left at CloudWatch's defaults, success is green, failed is orange, blocked is red, new lockouts is black, so the line colors carry the same meaning they would anywhere else, red is bad, green is good.

Latency: P50 and P95 plotted together rather than average and P95. Average is a poor summary statistic for latency because a small number of very slow requests barely move it, a handful of 5-second outliers among thousands of fast ones can leave the average looking fine. P50 and P95 side by side show the gap directly: if they track closely, the service is behaving uniformly; if P50 stays low while P95 climbs, a slice of requests are having a meaningfully worse experience than everyone else, which average would hide.

Error rate % over time and Authenticated requests: time-series versions of two of the top-row single values, for spotting trends rather than a single snapshot.

Saturation: CPU, memory, and disk from the CloudWatch agent, plotted together since they represent instance-level resource pressure. Each metric is referenced with its exact published dimensions, InstanceId, and for CPU and disk, additional dimensions like cpu and device, since CloudWatch treats a metric name without dimensions as a different metric entirely from the same name with dimensions attached.

## Screenshots

`evidence/dashboard-screenshots/dashboard-bruteforce-window.png` shows the full dashboard during the incident window (see INCIDENTS.md), request rate, error rate, latency, and saturation all in one view. `normal-traffic.png` in the same folder shows the same dashboard under calm, low-volume traffic, the before half of that comparison.