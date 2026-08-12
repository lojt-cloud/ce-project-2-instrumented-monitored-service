#!/usr/bin/env bash
set -euo pipefail

# Run this on the EC2 instance to set up and start the app.
# Builds on Amazon Linux 2023 or Ubuntu with python3 available.
# The instance's IAM role must include cloudwatch:PutMetricData, or
# metric pushes will log warnings and the dashboard will stay empty.

APP_DIR="/opt/auth-service"
sudo mkdir -p "$APP_DIR"
sudo cp -r ./app/* "$APP_DIR"
cd "$APP_DIR"

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export AWS_REGION="us-east-1"
export CLOUDWATCH_NAMESPACE="AuthService"
export PYTHONUNBUFFERED=1

nohup venv/bin/gunicorn -w 1 -b 0.0.0.0:8080 server:app > server.log 2>gunicorn-error.log &

echo "auth service started on port 8080"