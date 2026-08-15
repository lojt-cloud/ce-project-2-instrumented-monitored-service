# ce-project-2-instrumented-monitored-service

A user authentication service built with Flask, instrumented with structured logging, custom CloudWatch metrics, and CloudWatch alarms.
It demonstrates observability practices, instrumentation, dashboards, alerting, and incident response, on a single EC2 instance.

## What it does

The service exposes registration, login, logout, and session lookup endpoints, backed by an in-memory user store. Failed login attempts are tracked per account. After 5 consecutive failures, the account locks for 5 minutes. That lockout is also the target of this project's incident simulation, a brute force attack against a single account.

## Endpoints

- `POST /auth/register` - create a user
- `POST /auth/login` - authenticate, returns a session token
- `POST /auth/logout` - invalidate a session token
- `GET /auth/me` - return the authenticated user for a valid token
- `GET /health` - health check, no auth required

## Running locally

```bash
cd app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export AWS_REGION=us-east-1
export CLOUDWATCH_NAMESPACE=AuthService
python server.py
```

## Running on EC2

See docs/deployment.md for the full walkthrough: launching the instance, the IAM role, installing the CloudWatch agent, SNS, and applying the dashboard and alarms. Once the instance is up and the repo is cloned, deploying the app itself is one command from the repo root:

```bash
bash app/deploy.sh
```

The app runs on port 8080 behind a single Gunicorn worker, a deliberate choice to keep the in-memory user and session state consistent across requests rather than split across processes (see ARCHITECTURE.md). The instance's IAM role needs `cloudwatch:PutMetricData` and log-writing permissions, `CloudWatchAgentServerPolicy` covers both.

## Testing

```bash
curl -X POST http://localhost:8080/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"correct horse"}'

curl -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"correct horse"}'

curl http://localhost:8080/health
```

For load testing, Apache Bench works with a saved JSON payload:

```bash
echo '{"username":"alice","password":"correct horse"}' > /tmp/login_payload.json
ab -n 200 -c 1 -p /tmp/login_payload.json -T application/json http://localhost:8080/auth/login
```

Keep concurrency at 1 for a healthy baseline. Higher concurrency queues requests behind the single worker and inflates latency on its own, unrelated to any real problem, see ALERTING.md for why that matters. The brute force incident simulation itself is documented in INCIDENTS.md.

## Observability

- Structured logs and custom metrics: INSTRUMENTATION.md
- Dashboard design: MONITORING.md, and docs/dashboard-guide.md for how to read it
- Alerts: ALERTING.md
- Incident response: INCIDENTS.md
- Deployment: docs/deployment.md
- General troubleshooting: docs/runbook.md

## Screenshots

`evidence/dashboard-screenshots/` has the dashboard during the incident window and a calm baseline for comparison. `evidence/alert-screenshots/` has the alarm configuration, the SNS notification email, and the warning-versus-critical subscription state behind the open incident in INCIDENTS.md. `evidence/incident-screenshots/` has the raw log evidence, metric data, and alarm history table behind the root cause analysis in INCIDENTS.md. `architecture-diagram.png` at the repo root is referenced from ARCHITECTURE.md.

# Reflection

This section covers what I struggled with while building this project and what I learned from it.

## My prior experience with Python

Before this project my Python knowledge was minimal, a simple FizzBuzz and a rock-paper-scissors game was roughly the ceiling of what I could write from zero.
Flask, Gunicorn, and worker processes were all new to me. I had a rough mental model of what the system would do in the background, but seeing the actual lines of code felt like being out of my depth fast.

## New things I learned

Running Gunicorn with multiple workers means multiple copies of the app itself. Since I only had an EC2 instance and no database, a request from the same user could land on a different worker than a previous one, and that worker wouldn't have seen it, the state would only exist in whichever worker's memory it happened to land on.
Each worker can't see another worker's memory, so inconsistent state would result. Because of this I decided to run with a single worker, with the tradeoff that latency increases as requests queue up behind each other.
This also turned out to be useful for seeing metrics on the dashboard and understanding why P95 latency matters more than average.
Also, since the app runs on the EC2 instance's memory, any crash or restart wipes everything, all the registered users, all the sessions. I chose to keep it this way so the project stayed focused on observability and troubleshooting rather than persistence.

## Where I struggled

Seeing the bigger picture of how each new component, the Gunicorn runner, the Flask app, connects to the rest of the system.
Keeping things simple and not falling into too much detail. Focusing on the main goal is hard when I keep wanting to add more features and polish things further.
Setting up the dashboard and knowing which metrics I actually needed to retrieve, so I wouldn't end up with false data or no data at all (saturation was the tricky one).

## What I would do differently next time

Add an actual database so I could run more workers in parallel. Instead of the single worker being the latency bottleneck, I'd be able to see other causes of latency too.
Add a smarter signal for account lockouts instead of a manual check, the alarm can't tell a real attacker from someone who forgot their password.
Fix the boto3 timeout behavior. With one worker doing everything, a slow response from CloudWatch's own API can stall the whole process for a while (timeout, waiting for response, retrying the connection). Lowering the default timeout and retry settings would fix that.

## What I'm proud of

Forcing myself to write this in Python instead of using the provided base code for the project.
