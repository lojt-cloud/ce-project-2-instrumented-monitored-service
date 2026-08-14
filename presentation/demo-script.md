# Demo script

Full run-through for the 20-minute presentation, built from the outline. Bracketed lines are stage directions, not spoken text.

## My build

[Open on the title slide]

This is an authentication service. Registration, login, logout, session lookup, with structured logging, custom CloudWatch metrics, a dashboard, and tiered alarms wired around it. 
The point of the project isn't the auth app itself, it's everything watching it.

## The setup

- One Flask app on one EC2 instance, running behind Gunicorn with a single worker.
- No database. Flask holds everything in memory in one process.
- Restart or crash, all state is gone. That's a scope decision for a short exercise, not an oversight, say that plainly if anyone looks surprised.

## Why one worker

- Users, sessions, and lockout counts all live in the memory of that one Flask process.
- Two workers means two separate copies of that memory, and one worker has no way to see what the other is holding. A user registered on one could fail to be found on the other.
- That tradeoff shows up directly in latency, one worker means requests queue behind each other instead of running in parallel.
- bcrypt is what authenticates a login or hashes a new password on registration, and it's deliberately slow. That cost runs inside this same single worker, on every request, which is exactly why the queuing matters. Comes back up in the alerting section.

## Architecture

[Point at the diagram, trace left to right]

- A client request hits the Flask app.
- The Flask app does two things at the same time, not sequentially: writes a JSON log line to server.log, and pushes a custom metric straight to CloudWatch Metrics through boto3.
- Why push instead of deriving the metric from the log later: it shows up immediately, without waiting on log shipping to catch up.
- The response goes back with an X-Correlation-ID header, either the same one the request came in with, or a freshly generated one if it didn't have one.
- Separately, server.log gets tailed by the CloudWatch agent, which ships entries to CloudWatch Logs and also publishes CPU, memory, and disk to CloudWatch Metrics.
- CloudWatch Metrics feeds two things: the dashboard, and the alarms.
- Alarms feed SNS, SNS sends the email.

## Instrumentation

Logging side:

- structlog, JSON only, no plain text lines mixed in.
- Every request gets a correlation ID, either newly generated or pulled from the incoming header, bound to the log context, and echoed back in the response.
- Three log levels: INFO for normal outcomes, WARNING for an abnormal but handled case like a lockout, ERROR reserved for unhandled failures.

Metrics side:

- Six custom metrics under the AuthService namespace: login_success_total, login_failed_total, login_blocked_total, account_lockouts_total, authenticated_requests_total, api_latency_ms.
- The pairing that matters most: login_failed_total climbing followed by account_lockouts_total climbing is the actual signature of an attack against a specific account. 
- That pairing is what the live demo shows next.

## Live demo

[Terminal and dashboard both visible, dashboard on a fresh time range]

1. Kick off a small amount of normal traffic first, so the dashboard has a calm baseline on screen before anything happens. If you don't already have a script for this, a quick loop works:

```bash
BASE_URL="http://<public-ip>:8080" ./scripts/simulate-normal-traffic.sh
```

2. While that runs, give the dashboard a fast walkthrough: top row for at-a-glance status, Login outcomes and Latency underneath for the trend, Saturation at the bottom for the host itself. 
Keep this short, already covered the why in the architecture section, this is just orienting the audience to where to look.

3. Run the brute force script:

```bash
BASE_URL="http://<public-ip>:8080" ./scripts/simulate-brute-force.sh
```

4. Let the SNS email land, screen-share your inbox if you can, then stop and ask the room directly: "What do you think just happened?" Let a few people answer before confirming anything.

5. Refresh the dashboard and give the room a concrete choice, paste something like this into the chat:

   A) Someone's forgotten their password
   B) This is a brute force attack against one or more accounts
   C) The monitoring itself is broken

   Take the vote, then move into the incident response section to actually settle it with evidence instead of a guess.

## Incident response

[Say the framing out loud before touching anything]: "I'm going to use RED to check whether this is a real failure or just noise, then USE to rule the host itself in or out."

RED:

- Rate: point at Login outcomes, the failed line climbing from flat.
- Errors: point at Error rate %, pegged near 100% for the window, that's the line that separates this from ordinary background noise.
- Duration: point at Latency, P95 crossing the warning and critical thresholds.

USE, to rule out the host as the cause:

- Utilization: CPU utilization single value, note the live number.
- Saturation: the CPU/memory/disk time series staying flat and low through the spike, that rules the host out, the latency bump is queuing under one worker, not resource exhaustion.

[Switch to CloudWatch Log Analytics, select the log group]

Query for the failed-login window, grouped by username and IP:

```
fields @timestamp, username, ip, correlation_id
| filter event = "login_failed"
| stats count(*) as failures by username, ip
| sort failures desc
```

Point out the same IP across every row, one row per account, that's the actual evidence behind "brute force" rather than "several people forgot their passwords."

Query for the lockout timing check on one account:

```
fields @timestamp, username, ip
| filter event = "login_failed" and username = "confirmrun1"
| sort @timestamp asc
```

Point at the gaps between timestamps: seconds apart reads as a person, sub-second apart reads as a script.

Conclusion of the cause: state it as one sentence. Same source IP, sequential accounts, evenly-paced automated attempts, this is a real brute force attempt, confirmed by the logs, not assumed from the dashboard alone.

Timeline recap: failed logins spiked in the 11:57 minute, the failed-login alarms fired within about two minutes, the lockout alarm followed once accounts crossed five failures, and latency crossed both thresholds in the same window from the concurrent load, not from anything actually broken.

## Alerting and response

[Show config/alarms.json on screen]

Five alarms, two signals: login failures, the security-relevant signal this whole scenario is built around, and latency, the performance signal every service needs regardless of what it does.

FailedLogins-Warning at 10 a minute, FailedLogins-Critical at 25. Ten alone could be typos, twenty-five is well past anything normal traffic produces. Both run on a 180-second period rather than 60, because a burst that straddles a minute boundary can dodge a 60-second window even with more evaluation periods stacked on, only widening the period itself catches it reliably, that's from testing this against a live attack and watching the first version miss.

AccountLockout-Critical at a threshold of 1, the strongest signal of the five, since it only fires once an account has already crossed the app's own five-failure defense.

Latency-Warning at 500ms, Latency-Critical at 1000ms. The natural floor here is around 300ms, mostly bcrypt's deliberately expensive check. Say the caveat plainly: single worker means concurrent legitimate traffic alone can push P95 past even the critical line with nothing actually broken, a latency alarm is a prompt to check for a concurrency spike before assuming a defect.

Two SNS topics, warning and critical, kept separate so the two severities never look identical in an inbox.

## Learning and improvement

- A point-in-time check lies to you. describe-alarms looks identical whether an alarm never fired or fired and already recovered. Only alarm history tells the difference.
- A burst that doesn't align to a clean minute boundary can beat a short evaluation period even after adding more evaluation periods. Widening the period itself is what actually fixes it, not just adding more of them.

## Q&A

[Open the floor] "Happy to take questions, or dig into anything you want to see live again."

## Bye

Thanks for watching.