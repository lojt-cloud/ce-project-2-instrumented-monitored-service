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

