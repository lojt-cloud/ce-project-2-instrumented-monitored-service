# Instrumentation

## Logging strategy

The app uses structlog configured to emit JSON. Every request gets a correlation ID, either generated fresh or taken from an incoming `X-Correlation-ID` header, bound to the log context for the duration of the request, and returned in the response headers.
This makes it possible to trace a single request across log lines in CloudWatch Logs Insights.

Log levels:

- INFO: normal outcomes (`user_registered`, `login_success`, `logout`)
- WARNING: abnormal but handled conditions (`login_blocked_locked_account`, `account_locked`, `metric_push_failed`)
- ERROR: reserved for unhandled failures. Not currently triggered by the app; would cover something like a crashed dependency.

## Example log entries

```json
{"event": "login_success", "username": "alice", "ip": "203.0.113.42", "correlation_id": "3f2a1c9e-91d4-4b3a-9c2e-1a2b3c4d5e6f", "level": "info", "timestamp": "2026-08-12T10:15:32.123Z"}
```

```json
{"event": "account_locked", "username": "bob", "failed_attempts": 5, "ip": "203.0.113.99", "level": "warning", "correlation_id": "9d41e2ab-77f0-4c1a-8e3d-2b3c4d5e6f7a", "timestamp": "2026-08-12T10:16:01.456Z"}
```

## Custom metrics

Namespace: `AuthService` (configurable through `CLOUDWATCH_NAMESPACE`)

| Metric                         | Type  | What it measures                                                 |

| `login_success_total`          | Count | Successful logins                                                |
| `login_failed_total`           | Count | Failed login attempts, wrong credentials                         |
| `login_blocked_total`          | Count | Login attempts rejected because the account was already locked   |
| `account_lockouts_total`       | Count | Accounts that crossed the failure threshold and got locked       |
| `authenticated_requests_total` | Count | Requests to `/auth/me` with a valid token |
| `api_latency_ms`               | Milliseconds | Per-request latency, measured in the `after_request` hook |

`login_failed_total` and `account_lockouts_total` are the two metrics the brute force incident scenario depends on.
A spike in one followed by the other is the signature of an attack against a single account.

## Correlation ID implementation

Generated with `uuid4` if not supplied by the client, bound to structlog's context vars in a `before_request` hook, and cleared in `after_request`.
If another system called this service, it could supply its own `X-Correlation-ID` and get it echoed back, letting both sides' logs be searched with the same identifier.
Nothing in this project currently calls it that way, but the support costs nothing to have in place.
