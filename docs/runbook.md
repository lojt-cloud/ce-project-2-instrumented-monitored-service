# Runbook

General operational troubleshooting for the service itself, not alarm response (see ALERTING.md) or how to read the dashboard (see docs/dashboard-guide.md).

## App not responding

Check the process is actually running: `ps aux | grep gunicorn`. Check the health endpoint: `curl http://localhost:8080/health`. If neither works, check `gunicorn-error.log` for a crash reason before restarting blind.

Restart: `sudo pkill -f gunicorn`, then `bash app/deploy.sh` from the repo root.

## Redeploying after a code change

Commit and push from wherever the change was made. On the instance: `git pull`, then kill and restart gunicorn the same way as above.

If `deploy.sh` fails with a permission denied error on `/opt/auth-service`, that directory has stale files owned by a different user from a previous run. Wipe it first: `sudo rm -rf /opt/auth-service`, then rerun `deploy.sh`, the script recreates it with correct ownership.

## Metrics not showing up in CloudWatch

Confirm the IAM role is actually attached and vending credentials, from the instance:

TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/; echo

Should print the role name. If it doesn't, confirm from your local machine (not the instance) whether the profile is attached:

aws ec2 describe-instances --instance-ids <instance-id>
--query 'Reservations[0].Instances[0].IamInstanceProfile'

If metrics exist but a dashboard widget shows no data, check dimensions before anything else. A metric published with dimensions (`InstanceId`, `cpu`, and so on) is a different metric entirely from the same name with no dimensions specified. The widget needs the exact dimension set the metric was actually published with.

## Logs not showing up in CloudWatch

Confirm the agent is running: `sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status`. Confirm `server.log` has content locally first, before assuming the agent is the problem, `cat /opt/auth-service/server.log`.

`/health` doesn't write a log line by design, hitting it alone won't prove anything. Use an endpoint that actually logs, `/auth/register` or `/auth/login`, to test the full pipeline.

## Account locked during testing

Lockouts last 5 minutes (`LOCKOUT_DURATION_SECONDS` in `config.py`) and clear automatically, there's no manual unlock. Restarting the app also clears it, but that wipes every registered user and session along with it, only do that outside of a live demo.

## Local machine vs EC2 instance

AWS control-plane commands, dashboards, alarms, SNS, `describe-instances`, always run from your local machine, where your full AWS CLI credentials live. Anything touching the running app, its logs, or its files runs over SSH on the instance. If a command behaves unexpectedly, check `whoami` and `hostname` first to confirm which machine it actually ran on.