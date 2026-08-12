import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import boto3
import structlog
from flask import Flask, g, jsonify, request

from config import Config

app = Flask(__name__)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger()

cloudwatch = boto3.client("cloudwatch", region_name=Config.AWS_REGION)

# In-memory stores. State resets on restart, which is acceptable for this
# project's scope and demo window. A real deployment would back these with
# a database.
users = {}
login_state = {}
sessions = {}


def put_metric(name, value=1, unit="Count"):
    # Metric pushes are non-fatal. A missing IAM permission or a network
    # blip should not take down a login request.
    try:
        cloudwatch.put_metric_data(
            Namespace=Config.CLOUDWATCH_NAMESPACE,
            MetricData=[{"MetricName": name, "Value": value, "Unit": unit}],
        )
    except Exception as exc:
        log.warning("metric_push_failed", metric=name, error=str(exc))


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash)


def is_locked(username):
    state = login_state.get(username)
    if not state or not state.get("locked_until"):
        return False
    return datetime.now(timezone.utc) < state["locked_until"]


def register_failure(username):
    state = login_state.setdefault(
        username, {"failed_attempts": 0, "locked_until": None}
    )
    state["failed_attempts"] += 1
    if state["failed_attempts"] >= Config.MAX_FAILED_ATTEMPTS:
        state["locked_until"] = datetime.now(timezone.utc) + timedelta(
            seconds=Config.LOCKOUT_DURATION_SECONDS
        )
        log.warning(
            "account_locked", username=username, failed_attempts=state["failed_attempts"]
        )
        put_metric("account_lockouts_total")


def reset_failures(username):
    login_state[username] = {"failed_attempts": 0, "locked_until": None}


@app.before_request
def start_request():
    g.start_time = time.time()
    g.correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(correlation_id=g.correlation_id)


@app.after_request
def finish_request(response):
    latency_ms = (time.time() - g.start_time) * 1000
    put_metric("api_latency_ms", value=latency_ms, unit="Milliseconds")
    response.headers["X-Correlation-ID"] = g.correlation_id
    structlog.contextvars.clear_contextvars()
    return response


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    if username in users:
        return jsonify({"error": "username already exists"}), 409

    users[username] = {"password_hash": hash_password(password)}
    login_state[username] = {"failed_attempts": 0, "locked_until": None}

    log.info("user_registered", username=username)
    return jsonify({"status": "registered"}), 201


@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    if is_locked(username):
        log.warning("login_blocked_locked_account", username=username)
        put_metric("login_blocked_total")
        return jsonify({"error": "account is locked, try again later"}), 423

    user = users.get(username)
    if not user or not check_password(password, user["password_hash"]):
        register_failure(username)
        log.info("login_failed", username=username)
        put_metric("login_failed_total")
        return jsonify({"error": "invalid credentials"}), 401

    reset_failures(username)
    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "username": username,
        "expires_at": datetime.now(timezone.utc)
        + timedelta(seconds=Config.SESSION_TOKEN_TTL_SECONDS),
    }

    log.info("login_success", username=username)
    put_metric("login_success_total")
    return jsonify({"token": token}), 200


@app.route("/auth/logout", methods=["POST"])
def logout():
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    sessions.pop(token, None)
    log.info("logout", token_present=bool(token))
    return jsonify({"status": "logged out"}), 200


@app.route("/auth/me", methods=["GET"])
def me():
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    session = sessions.get(token)

    if not session or datetime.now(timezone.utc) > session["expires_at"]:
        return jsonify({"error": "invalid or expired token"}), 401

    put_metric("authenticated_requests_total")
    return jsonify({"username": session["username"]}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)