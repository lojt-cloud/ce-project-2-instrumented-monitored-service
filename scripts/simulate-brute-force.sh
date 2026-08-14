#!/usr/bin/env bash
set -euo pipefail

# Simulates a brute force attack against /auth/login for the incident
# Run this from your local machine (not over SSH), so the source IP in the app logs is real rather than the instance's own loopback address.
# Usage:
#   BASE_URL="http://<public-ip>:8080" ./scripts/simulate-brute-force.sh
#
# Registers NUM_ACCOUNTS fresh accounts with a real password, then hits each one with the wrong password ATTEMPTS_PER_ACCOUNT times. 
#The app locks an account after 5 consecutive failures (see MAX_FAILED_ATTEMPTS in app/config.py), so the default of 5 attempts triggers one lockout per account.

BASE_URL="${BASE_URL:-http://<PUBLIC_IP>:8080}"
PREFIX="${PREFIX:-confirmrun}"
PASSWORD="${PASSWORD:-RealPassword123!}"
WRONG_PASSWORD="${WRONG_PASSWORD:-wrongpassword}"
NUM_ACCOUNTS="${NUM_ACCOUNTS:-6}"
ATTEMPTS_PER_ACCOUNT="${ATTEMPTS_PER_ACCOUNT:-5}"
DELAY_SECONDS="${DELAY_SECONDS:-1.5}"

echo "start: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

for i in $(seq 1 "$NUM_ACCOUNTS"); do
  USERNAME="${PREFIX}${i}"
  curl -s -X POST "$BASE_URL/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" > /dev/null
  sleep 0.3
done

for i in $(seq 1 "$NUM_ACCOUNTS"); do
  USERNAME="${PREFIX}${i}"
  for attempt in $(seq 1 "$ATTEMPTS_PER_ACCOUNT"); do
    curl -s -X POST "$BASE_URL/auth/login" \
      -H 'Content-Type: application/json' \
      -d "{\"username\":\"$USERNAME\",\"password\":\"$WRONG_PASSWORD\"}" > /dev/null
    sleep "$DELAY_SECONDS"
  done
done

echo "end: $(date -u +%Y-%m-%dT%H:%M:%SZ)"