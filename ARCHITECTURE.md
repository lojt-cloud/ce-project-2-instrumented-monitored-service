# Architecture

## Overview

A single EC2 instance runs the Flask authentication service behind Gunicorn. The CloudWatch agent runs on the same instance, tailing the application's JSON log file and collecting OS-level metrics (CPU, memory, disk). 
The application pushes custom metrics directly to CloudWatch through boto3. 
CloudWatch alarms evaluate those metrics and publish to an SNS topic, which sends an email notification.

## Components

- Flask app (`app/server.py`): handles registration, login, logout, session lookup, and health checks. Tracks failed login attempts and account lockouts in memory.
- CloudWatch agent: ships app logs to CloudWatch Logs, publishes CPU, memory, and disk metrics.
- CloudWatch custom metrics: pushed directly from the app through boto3, covering login outcomes, lockouts, authenticated requests, and API latency.
- CloudWatch dashboard: visualizes Golden Signals alongside the login-specific metrics.
- CloudWatch alarms and SNS: tiered warning and critical alerts on error rate and latency, defined in `config/alarms.json`.

## Data flow

1. A client sends a request to the Flask app.
2. The app assigns a correlation ID, generated fresh or taken from an incoming `X-Correlation-ID` header, and writes a structured JSON log line for the request.
3. After the response is built, the app pushes the relevant metrics (login outcome, latency) to CloudWatch through boto3.
4. The CloudWatch agent tails the log file on its own schedule and forwards entries to CloudWatch Logs, and reports OS metrics separately.
5. CloudWatch alarms evaluate the published metrics on a 1-minute period and notify the SNS topic when a threshold is breached.

## Why a single EC2 instance

The project's scope is observability, not infrastructure complexity. One instance keeps the deployment surface small and lets the CloudWatch agent handle both log shipping and OS metrics from a single place, without a load balancer, auto scaling group, or container orchestration the rubric doesn't call for.

## State and persistence

Users, sessions, and lockout state live in memory in the Flask process. This is a deliberate scope decision for a 3-day observability exercise, not an oversight. 
A restart clears all state, which is fine for the demo and incident simulation, but would need to change, for example to DynamoDB or RDS, before this ran in production.

This also constrains the app to a single Gunicorn worker. Each worker is a fully separate process with its own memory, so running more than one would mean each worker holding its own separate, inconsistent copy of the `users` and `sessions` dictionaries, a user registered on one worker could fail to be found on another. The tradeoff of a single worker is that requests are handled one at a time rather than in parallel, which shows up directly in the latency metrics under concurrent load. 
A production version would move this state to something external, at which point running multiple workers would be safe.