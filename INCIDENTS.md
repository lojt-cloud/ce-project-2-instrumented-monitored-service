# Incidents

## Incident: warning-tier alert notifications not delivering

### Summary

A simulated brute force attack against `/auth/login` was run three separate times over the course of one day to validate detection and alerting. Across all three runs, every alarm correctly detected the attack and transitioned to ALARM within two minutes, confirmed directly from CloudWatch's own alarm state history, not just a point-in-time check. The actual problem found during this exercise is different from a detection failure: the SNS subscription behind `auth-service-warning` is in a `Deleted` state and is not delivering warning-tier notifications, while the alarms underneath it fire correctly every time. This incident documents the detection validation, the two alarm configuration changes made along the way, and the still-open investigation into the notification failure.

### Timeline (2026-08-14, UTC, except where noted)

**Run 1, 08:26-08:29.** Six accounts, five failed login attempts each against `/auth/login`, real source IP 143.179.136.227, fifth attempt on each account triggers `account_locked`. `login_failed_total` and `account_lockouts_total` both spike in the 08:29:00 bucket (27.0 and 6.0). All three relevant alarms were still on their original settings at this point (`Period=60`, `EvaluationPeriods=1`, `DatapointsToAlarm=1`) and all three fired correctly: `AuthService-FailedLogins-Critical` at 08:30:18, `AuthService-FailedLogins-Warning` at 08:30:42, `AuthService-AccountLockout-Critical` at 08:30:49, each roughly 90 seconds after the breach. All three cleared back to OK around 08:36-08:37 once the burst ended, which is expected behavior for a single-period alarm with no further activity, not a sign anything was wrong.

**Between 08:37 and 09:11, fix 1 applied to all three alarms.** `EvaluationPeriods` widened from 1 to 3 and `DatapointsToAlarm` from 1 to 2, `Period` left at 60. Confirmed from the alarm history: `AuthService-AccountLockout-Critical`'s next transition after run 1 already shows the wider evaluation window in its `StateReasonData`.

**Run 2, 09:11-09:12.** Six new accounts (`bruteuser1` through `bruteuser6`), same pattern, same source IP. 30 `login_failed` and 6 `account_locked` events logged, split across the 09:11:00 and 09:12:00 buckets (4.0 and 2.0 lockouts respectively). `AuthService-AccountLockout-Critical` fired at 09:13:36, about a minute and a half after the run ended, using fix 1's settings, two breaching one-minute buckets easily satisfied its `DatapointsToAlarm=2`. `AuthService-FailedLogins-Warning` and `AuthService-FailedLogins-Critical` did not fire on fix 1 alone. The 30 failed logins split across two consecutive 60-second buckets, and neither bucket alone reached the 25 or even reliably cleared 10 threshold on its own, a burst that doesn't align to a minute boundary can dodge a same-minute evaluation window even with more evaluation periods added. 


**Between 09:12 and 09:25, fix 2 applied to the two FailedLogins alarms only.** `Period` widened from 60 to 180, `EvaluationPeriods` reduced from 3 to 2, `DatapointsToAlarm` from 2 to 1. A 180-second bucket comfortably contains a burst regardless of where it falls relative to a minute boundary. `AuthService-FailedLogins-Critical` fired at 09:25:02 and `AuthService-FailedLogins-Warning` at 09:25:24, both against the 09:10:00-09:13:00 bucket (30.0 failed logins, correctly clearing both thresholds), both cleared back to OK about two minutes later. `AuthService-AccountLockout-Critical` was left on fix 1, already proven to work. The two latency alarms were left unchanged throughout, nothing in this investigation showed their metric pipeline had the same problem.

**Confirmation run, 11:58:59-12:00:07.** Six new accounts (`confirmrun1` through `confirmrun6`), same pattern, run from a local machine rather than over SSH so the source IP is genuine, script and full command log in `scripts/simulate-brute-force.sh`. This run used the final, confirmed-live alarm configuration (see the table below) and is the clean, unambiguous evidence for this report.

### Final alarm configuration (confirmed live via `describe-alarms`, matches `config/alarms.json`)

| Alarm                                 | Period | EvaluationPeriods | DatapointsToAlarm | Threshold |

| `AuthService-FailedLogins-Warning`    | 180    | 2                 | 1                 | 10   |
| `AuthService-FailedLogins-Critical`   | 180    | 2                 | 1                 | 25   |
| `AuthService-AccountLockout-Critical` | 60     | 3                 | 2                 | 1    |
| `AuthService-Latency-Warning`         | 60     | 1                 | 1                 |  500 |
| `AuthService-Latency-Critical`        | 60     | 1                 | 1                 | 1000 |

### Confirmation run results, from CloudWatch's own alarm history

| Alarm                                 | OK to ALARM | ALARM to OK                  | Trigger data                              |

| `AuthService-FailedLogins-Warning`    | 12:00:24    | still in ALARM at write time | 27.0 failed logins, 11:57:00 bucket       |
| `AuthService-FailedLogins-Critical`   | 12:00:28    | still in ALARM at write time | 27.0 failed logins, 11:57:00 bucket       |
| `AuthService-AccountLockout-Critical` | 12:01:36    | 12:08:36                     | 5.0 lockouts at 11:59:00, 1.0 at 12:00:00 |
| `AuthService-Latency-Warning`         | 12:01:45    | 12:07:54                     | P95 1098ms, 12:00:00 bucket               |
| `AuthService-Latency-Critical`        | 12:01:04    | 12:07:04                     | P95 1098ms, 12:00:00 bucket               |

Every alarm detected the attack within two minutes of it starting. The two latency alarms firing was not staged, it's a real instance of the single-worker queuing tradeoff documented in ALERTING.md: six near-simultaneous registration and login calls, each doing a `bcrypt` hash, queued behind the single Gunicorn worker and pushed P95 latency to 1098ms, past both the 500ms and 1000ms thresholds. Screenshots: `evidence/dashboard-screenshots/dashboard-bruteforce-window.png`, `evidence/incident-screenshots/login-failed.png`, `evidence/incident-screenshots/alarm-state.png`, `evidence/incident-screenshots/metric-data-first-run.png`, `evidence/alert-screenshots/alarms-config-post-fix.png`, `evidence/alert-screenshots/email-alert.png`. `evidence/dashboard-screenshots/normal-traffic.png` is the calm, before-attack counterpart to the bruteforce-window shot.

### The open incident: `auth-service-warning` subscription

`aws sns list-subscriptions-by-topic` on `auth-service-warning` currently shows `SubscriptionArn: Deleted`. The topic's counterpart, `auth-service-critical`, shows a real, active subscription ARN and is confirmed working, it delivered the 09:25:02 email referenced above. 
Warning-tier alarms are firing correctly and on time, the same as critical-tier ones, but nobody is being notified when they do. `evidence/alert-screenshots/sns-subscription.png` shows both subscriptions side by side, `Deleted` on the warning topic against a live ARN on the critical topic. 
This has happened more than once. CloudTrail shows `auth-service-warning` subscribed on 2026-08-13 at 08:12:26, then resubscribed twice more on 2026-08-14 at 09:25:09 and 09:26:36, ninety seconds apart, suggesting a prior attempt to fix the same problem that day. 
None of these attempts left the subscription in a working state.

A `Deleted` status can only happen after a subscription was confirmed and later unsubscribed. Neither of those two events shows up anywhere in this account's CloudTrail history for this topic, across `Subscribe`, `ConfirmSubscription`, and `Unsubscribe` lookups covering 2026-08-11 through 2026-08-14. The only `ConfirmSubscription` event in the entire account history is for an unrelated topic (`CloudWatchAlerts`), confirmed manually via the AWS CLI. Whatever confirmed and then killed the `auth-service-warning` subscription did not go through a path CloudTrail's default 90-day Event History captures, most likely SNS's public, unauthenticated one-click confirm and unsubscribe URLs, which every notification email includes in its footer alongside the alarm content. A browser extension, antivirus tool, or email link-scanner visiting every link in an incoming message would explain both the silent failure and the lack of a CloudTrail trail for it, but this remains a suspected cause, not a confirmed one. That gap is itself worth noting: the default CloudTrail Event History is not a complete audit log for this kind of failure.

### Status

Open. `auth-service-critical` is confirmed working. `auth-service-warning` needs to be resubscribed using the raw email `Token` and `aws sns confirm-subscription` directly, rather than clicking the link in a rendered email client, to avoid whatever is auto-visiting the unsubscribe link on subsequent notification emails. Not yet done as of this writing.

### Lessons learned

A point-in-time `describe-alarms` check can look identical whether an alarm never fired or fired and already recovered, both show up as `OK` with a missing-data reason. `describe-alarm-history` is what actually tells the difference, and it's what settled every question in this investigation that a single snapshot could not.

A burst that doesn't align to a minute boundary can defeat a short evaluation period even after widening `EvaluationPeriods`, only widening `Period` itself reliably contains it, which is why fix 2 was necessary in addition to fix 1.

An alarm firing correctly is not the same as a human finding out about it. The detection side of this project worked every single time it was tested. The delivery side failed, repeatedly, and the standard audit tooling couldn't fully explain why, that gap between "the system detected it" and "someone was told" is the more realistic failure mode to design around in a production system.
