# ce-project-2-instrumented-monitored-service

A user authentication service built with Flask, instrumented with structured logging, custom CloudWatch metrics, and CloudWatch alarms. It demonstrates observability practices, instrumentation, dashboards, alerting, and incident response, on a single EC2 instance.

## What it does

The service exposes registration, login, logout, and session lookup endpoints, backed by an in-memory user store. Failed login attempts are tracked per account. After 5 consecutive failures, the account locks for 5 minutes. That lockout is also the target of this project's incident simulation, a brute force attack against a single account.

## Endpoints

- `POST /auth/register` - create a user
- `POST /auth/login` - authenticate, returns a session token
- `POST /auth/logout` - invalidate a session token
- `GET /auth/me` - return the authenticated user for a valid token
- `GET /health` - health check, no auth required

## Running locally

cd app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export AWS_REGION=us-east-1
export CLOUDWATCH_NAMESPACE=AuthService
python server.py

## Running on EC2

See docs/deployment.md for the full walkthrough: launching the instance, the IAM role, installing the CloudWatch agent, SNS, and applying the dashboard and alarms. Once the instance is up and the repo is cloned, deploying the app itself is one command from the repo root:
bash app/deploy.sh

The app runs on port 8080 behind a single Gunicorn worker, a deliberate choice to keep the in-memory user and session state consistent across requests rather than split across processes (see ARCHITECTURE.md). The instance's IAM role needs `cloudwatch:PutMetricData` and log-writing permissions, `CloudWatchAgentServerPolicy` covers both.

## Testing

curl -X POST http://localhost:8080/auth/register
-H 'Content-Type: application/json'
-d '{"username":"alice","password":"correct horse"}'

curl -X POST http://localhost:8080/auth/login
-H 'Content-Type: application/json'
-d '{"username":"alice","password":"correct horse"}'

curl http://localhost:8080/health

*For load testing*, Apache Bench works with a saved JSON payload:

echo '{"username":"alice","password":"correct horse"}' > /tmp/login_payload.json
ab -n 200 -c 1 -p /tmp/login_payload.json -T application/json http://localhost:8080/auth/login

Keep concurrency at 1 for a healthy baseline. Higher concurrency queues requests behind the single worker and inflates latency on its own, unrelated to any real problem, see ALERTING.md for why that matters. The brute force incident simulation itself is documented in INCIDENTS.md.

## Observability

- Structured logs and custom metrics: INSTRUMENTATION.md
- Dashboard design: MONITORING.md, and docs/dashboard-guide.md for how to read it
- Alerts: ALERTING.md
- Incident response: INCIDENTS.md
- Deployment: docs/deployment.md
- General troubleshooting: docs/runbook.md


# Reflection 

This section ment to describe what challanges I faced during the creation of this project and what I've learnt from it. 

*My prior experience with Python*:  
Before this project my knowledge was minimal, simple fizzbuzz and a rock-paper-scissors game was roughly the ceiling of what I could write from zero. 
Flash, Gunicorn and worker processes were very much new to me. I had a mental model of what the system would do in the background, but seeing the lines of code felt like being out of the deep fast.


*New things I learnt*: 
Running Gunicorn with multiple workers means multiple copy of the app itself and since I only had an EC2 instance and no database to reach out for if a request comes in from the same user and not the same worker would pick up the request means that it would get stored on that workers memory. 
Each worker can't see over the others memory so inconsistent state would've occured. Because of this I decided to do with 1 worker with a tradeoff of latency would increase with every new request would come in. 
This also useful to get metrics visible in the dashboard and see the importance of p95 latency vs avarage.
Also since it runs on the ec2 intance if any crash or restart happens everything will be wiped. all the user login info, everything. For the simplicity of the project I choce it this way to actually focus on the observability and troubleshooting. 

*Where I struggled*: 

Seeing the bigger picture of each new component (gunicorn runner, flask app), how they connect to the whole system. 
Keeping the simpicity and not falling into too much details. Focusing on the main goal is hard when I have the temptation to add more and more features and polish is further and further. 

Setting up the dashboard and knowing what metrics I would need to retreive in order not to get false data or no data at all (saturation).


*What I would do differently next time *: 

Adding actual DB to it so can do more workers in paralell. Instead of bottlenecking the latency with this I would be able to see other causes of it also. 
Adding a smarter signal for account lockouts, not just a manual check. The alarm can't tell a real attacker from someone who forgott their password. 
boto3 timeout fix. Having 1 worker that does everything is a big bottleneck and in case of a slow respond time the proccess would be stuck there waiting up to several minutes (timeout, waiting for response, retrying connection). 
A solution for that would be to change the default settings for waiting/timeout and retries to a lower count. 

*What I'm proud of*: 

Forcing myself with the Python instead of using the provided preset base code option for this project.
