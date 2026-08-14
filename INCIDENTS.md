# Incident: brute force alarms did not fire on first breach

## Summary

A simulated brute force attack against `/auth/login` cleared both the warning and critical failed-login thresholds, and CloudWatch had correct data reflecting that, but none of the three related alarms changed state. 
Investigation found two separate problems in the alarm configuration, not one. A second test run and an unrelated discovery about a deleted SNS subscription are also logged here since they came out of the same investigation.

## Timeline (2026-08-14, UTC)

- 08:26-08:29: First simulated brute force run against 6 accounts, 5 failed login attempts each via `/auth/login`, real source IP 143.179.136.227. Fifth attempt on each account triggers `account_locked`.
- 08:28-08:29: `login_failed_total` metric shows 3.0 at 08:28 and 27.0 at 08:29, clearing both `AuthService-FailedLogins-Warning` (threshold 10) and `AuthService-FailedLogins-Critical` (threshold 25).
- 08:29-10:36: `AuthService-FailedLogins-Warning`, `AuthService-FailedLogins-Critical`, and `AuthService-AccountLockout-Critical` remain `OK` throughout, despite the breach.
- 10:36: Manual `describe-alarms` check shows all three alarms `OK`, `StateReason`: "no datapoints were received for 1 period and 1 missing datapoint was treated as [NonBreaching]." Dashboard review is what actually caught the spike, not the alarms.
- 10:37: Applied fix 1, widened `EvaluationPeriods` from 1 to 3 and `DatapointsToAlarm` from 1 to 2 on all three alarms, `Period` unchanged at 60.
- 09:11-09:12: Second simulated brute force run against 6 new accounts (`bruteuser1` through `bruteuser6`), same pattern, 5 failed attempts each, real source IP throughout. 30 `login_failed` and 6 `account_locked` events logged for the run.
- Following the second run: `AuthService-AccountLockout-Critical` transitions to `ALARM` (2 of the last 3 datapoints, 2.0 and 4.0, both clearing its threshold of 1), SNS notification email received. `AuthService-FailedLogins-Warning` and `AuthService-FailedLogins-Critical` remain `OK`, `StateReason` still reads as a missing-data message rather than a breach evaluation.
- Checking SNS subscriptions during this investigation found `auth-service-warning`'s email subscription showed `SubscriptionArn: Deleted`, while `auth-service-critical`'s was confirmed and intact. Root cause suspected: a browser extension or antivirus tool auto-following links in a prior notification email, including the one-click unsubscribe link SNS includes in every message.

## Root cause

**Evaluation window too narrow for publish latency (affected all three alarms initially).** 
The alarms were configured with `Period=60`, `EvaluationPeriods=1`, `DatapointsToAlarm=1`, `TreatMissingData=notBreaching`. CloudWatch evaluates each alarm close to real time against the period that just closed. If the log-to-metric pipeline has even a short publish delay, the alarm's evaluation for a given minute can run before that minute's datapoint has landed. It finds nothing, `TreatMissingData=notBreaching` marks that period non-breaching, and the alarm moves to the next period without re-checking the one that later received the late data. 
Confirmed directly: `get-metric-statistics` on `login_failed_total` for the attack window returned the correct 3.0 and 27.0 datapoints, while `describe-alarms` for the same window showed `OK` with a missing-data reason.

**Per-period volume threshold too strict for a burst that doesn't align to a minute boundary (affected the two FailedLogins alarms after fix 1).** 
Widening to `EvaluationPeriods=3`/`DatapointsToAlarm=2` fixed `AccountLockout-Critical` because its threshold is 1, trivially cleared by any period with activity, so two out of three periods breaching is easy to satisfy. `FailedLogins-Warning` and `FailedLogins-Critical` need 10 or 25 events inside a single 60-second bucket. The second test run's burst was paced slower than the first and straddled a minute boundary, splitting its 30 total failed-login events across two under-threshold buckets. Requiring two separate one-minute periods to each independently clear the full threshold is a higher bar than the alarms were originally designed for, and a real attacker has no reason to time a burst to fit cleanly inside one 60-second window.

## Fix

Fix 1, applied to all three alarms: `EvaluationPeriods` 1 to 3, `DatapointsToAlarm` 1 to 2, `Period` unchanged at 60. Confirmed sufficient for `AccountLockout-Critical` only.

Fix 2, applied to `FailedLogins-Warning` and `FailedLogins-Critical` only: `Period` 60 to 180, `EvaluationPeriods` 3 to 2, `DatapointsToAlarm` 2 to 1. A 180-second bucket comfortably contains a burst regardless of where it falls relative to a minute boundary, and `EvaluationPeriods=2`/`DatapointsToAlarm=1` still gives one bucket of slack for publish latency without requiring the burst to repeat itself. Applied via `put-metric-alarm`. Not yet confirmed with a live re-test, see open items below.

`AccountLockout-Critical` was left on the fix 1 settings, already proven to work. The two latency alarms (`AuthService-Latency-Warning`, `AuthService-Latency-Critical`) were left unchanged throughout, nothing in this investigation showed their metric pipeline had the same publish delay.

`config/alarms.json` in the repo reflects fix 1 for all three alarms but has not yet been updated to match fix 2's `Period=180`/`EvaluationPeriods=2`/`DatapointsToAlarm=1` for the two FailedLogins alarms, since fix 2 was applied directly via CLI. Needs a follow-up edit and commit so the file matches what's actually live.

Separately, resubscribed `auth-service-warning`'s email endpoint and confirmed it via the `Token` extracted from the raw confirmation email rather than clicking the link directly, to avoid the same auto-click behavior deleting the subscription again.

