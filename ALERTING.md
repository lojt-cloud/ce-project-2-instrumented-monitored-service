# Alerting

## Alert strategy

Five alarms, tiered warning and critical, covering two signals: login failures, the security-relevant signal this project's incident scenario is built around, and latency, the performance signal every service needs regardless of what it does. All five use a 1-minute period with a single-datapoint evaluation, tuned to fire fast rather than wait for the usual multi-datapoint confirmation, since this needs to demonstrate detection within a short demo window.

## Threshold justifications

`AuthService-FailedLogins-Warning`, more than 10 failed logins in a minute. Early signal. Could be normal noise, typos, forgotten passwords, or an attack just starting to ramp up. Not conclusive enough to be critical on its own.

`AuthService-FailedLogins-Critical`, more than 25 failed logins in a minute. Well above anything normal noise would produce, a strong brute-force indicator.

`AuthService-AccountLockout-Critical`, one or more lockouts in a minute. The strongest signal of the five. A lockout only fires once a specific account has crossed the app's own defended threshold of 5 consecutive failures, so unlike a raw failure count, it's close to unambiguous evidence rather than something that still needs interpretation.

`AuthService-Latency-Warning`, P95 above 500ms. Meaningfully above the service's natural floor, a single login request costs roughly 300ms on this hardware, most of it `bcrypt`'s password check, which is deliberately expensive by design.

`AuthService-Latency-Critical`, P95 above 1000ms.

One caveat worth stating plainly: this app runs a single Gunicorn worker, a deliberate choice to keep the in-memory user and session state consistent (see ARCHITECTURE.md). 
That means concurrent requests queue behind each other rather than processing in parallel, so a burst of simultaneous legitimate traffic can push P95 past even the critical threshold on its own, with nothing actually broken. 
A latency alarm firing is a prompt to check the Saturation and Request rate panels for a concurrency spike before assuming something is wrong.

## SNS topic configuration

Two topics, `auth-service-warning` and `auth-service-critical`, each with a single email subscription, confirmed and active. Warning-tier alarms notify the warning topic, critical-tier alarms notify the critical topic, so the two severities land as visibly different notifications rather than one undifferentiated stream.

## Response procedures

`AuthService-FailedLogins-Warning`: check the Login outcomes panel. If failures are concentrated on one or two accounts and trending up, treat it as a possible early attack and watch for escalation to critical or a lockout. If they're spread across many accounts at low volume, that's ordinary user error, no action needed.

`AuthService-FailedLogins-Critical`: query CloudWatch Logs Insights for `login_failed` events in the alarm window, grouped by `username` and by `ip`, to identify the targeted account and the source. Check whether `AuthService-AccountLockout-Critical` has also fired, that's the expected companion signal if the failures are concentrated on one account.

`AuthService-AccountLockout-Critical`: don't treat this as confirmed malicious on its own, a single lockout also looks exactly like a user who forgot their password. Query Logs Insights for the `login_failed` events on the affected username first and check two things: the time gaps between attempts, seconds apart suggests a person, sub-second apart suggests a script, and whether any other account also shows `account_locked` in the same window, one isolated lockout is more likely a forgotten password, several accounts locking out together is a much stronger signal of a real attack. Escalate as a confirmed incident only if the timing looks automated or multiple accounts are affected, otherwise this is most likely a user who needs a password reset. Either way, the `ip` from the logs is worth recording for any follow-up.

`AuthService-Latency-Warning`: check the Saturation panel for CPU pressure and the Request rate panel for a concurrency increase. Given the single-worker design, simultaneous requests alone can explain this without any actual defect.

`AuthService-Latency-Critical`: same investigation, escalated. If it correlates with a concurrent traffic spike, it's the known single-worker capacity limit, not a bug, worth noting as such rather than treated as a mystery. If it fires with low concurrent volume, check `server.log` for `metric_push_failed` warnings, since a slow or throttled call to CloudWatch's own API would add real latency to every request.