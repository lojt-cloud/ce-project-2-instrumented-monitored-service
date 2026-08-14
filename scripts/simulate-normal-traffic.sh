#!/usr/bin/env bash
set -euo pipefail

# Generates steady, normal login traffic for the live demo baseline, so the
# dashboard shows a calm, low-volume signal before the brute force script
# runs. See presentation/demo-script.md for where this fits in the demo.
#
# Usage:
#   BASE_URL="http://<public-ip>:8080" ./scripts/simulate-normal-traffic.sh
#
# Registers one account with a real password, then logs in with the correct
# password NUM_REQUESTS times, DELAY_SECONDS apart. Every request succeeds,
# so this only exercises login_success_total, not the failure or lockout
# metrics. Safe to run more than once, a repeat registration just returns a
# conflict response and the login loop still runs.

BASE_URL="${BASE_URL:-http://<PUBLIC_IP>:8080}"
USERNAME="${USERNAME:-demo_baseline}"
PASSWORD="${PASSWORD:-RealPassword123!}"
NUM_REQUESTS="${NUM_REQUESTS:-30}"
DELAY_SECONDS="${DELAY_SECONDS:-2}"

echo "start: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

curl -s -X POST "$BASE_URL/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" > /dev/null

for i in $(seq 1 "$NUM_REQUESTS"); do
  curl -s -X POST "$BASE_URL/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" > /dev/null
  sleep "$DELAY_SECONDS"
done

echo "end: $(date -u +%Y-%m-%dT%H:%M:%SZ)"