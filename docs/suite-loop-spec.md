# TestPilot Suite Loop — Design Spec v0.1

Test suites with an owner + a default runner, assignment/reminder/completion
notifications (email + in-app), closing the loop through the existing Issues board.

## Locked decisions
1. **Runner = manual run + review** — the agent does the clicking; a human triggers the
   suite and reviews results. No auto-run in this milestone.
2. **Reminders = per-suite cadence/due + a Celery-beat scan** that emails the runner
   (cc owner) when due/overdue. Beat does NOT auto-run.
3. **Channels = email + in-app notification center** (🔔 with unread state).
4. **People**: one owner + one *default* runner per suite (advisory, non-exclusive —
   any project member may run); every Run records the *actual* runner (`ran_by`).
5. **People link to real accounts**: new suite/run fields are User FKs; `Issue`
   gains `assignee_user_id` (kept alongside the legacy free-text `assignee`).

## Data model
- **TestSuite** (new): project_id, name, description, selection (case_ids | tag_filter),
  `owner_user_id`, `runner_user_id?`, `cadence` (none|daily|weekly|biweekly|monthly),
  `due_at?`, `last_run_id/last_status/last_run_at`, created_by, timestamps.
- **Run** (+): `suite_id?`, `ran_by_user_id?`, `trigger` (manual|suite).
- **Issue** (+): `assignee_user_id?` (FK; legacy `assignee` string kept for display/GitLab).
- **Notification** (new): user_id, type, title, body, link, suite_id?/run_id?/issue_id?,
  read_at?, emailed, created_at.

## Closed loop + notification matrix
| Event | Trigger | Recipients | Email | In-app |
|---|---|---|---|---|
| Suite assigned | set/change runner | runner | ✓ | ✓ |
| Due / overdue | beat scan of `due_at` | runner (cc owner) | ✓ | ✓ |
| Run completed | run finalize | owner + actual runner | ✓ (always on fail) | ✓ |
| Issue assigned | set assignee | assignee | ✓ | ✓ |
| Issue fixed | status→fixed | actual runner / owner | ✓ | ✓ |
| Verified | status→verified | owner | digest | ✓ |

Anti-spam: one run's failures collapse into a single email; in-app notifications dedupe
by (user,type,ref). A completed run advances `due_at` by the cadence.

## Reuse
- **Celery beat** (already running): add `scan_suite_reminders` (hourly) — email due/overdue.
- **mailer** (fixed): all email; `Notification.emailed` prevents double-send.
- **Issues board** (open→fixed→verified→closed + provenance): hook assign/fixed notifications.
- **Users/RBAC**: owner/runner/assignee are real Users; who-can-run = project membership.

## API
```
GET/POST   /projects/{pid}/suites
GET/PUT/DELETE /suites/{id}
POST       /suites/{id}/assign            {runner_user_id}
POST       /suites/{id}/run               -> Run(suite_id, ran_by=current), fan_out_run
GET        /notifications                 (current user; unread first)
GET        /notifications/unread-count
POST       /notifications/{id}/read  |  POST /notifications/read-all
```

## Frontend
- **Suites** tab per project: list (name/owner/runner/cadence/last status/next due),
  create/edit drawer, Run button.
- **🔔 notification center** in the top bar: unread badge, dropdown list, mark-all-read.
- **Run report**: "run by X".
- All controls use the shared shadcn components.

## Phasing
- **MVP (this milestone)**: TestSuite + assign + cadence/due + beat reminder + run-done
  email + in-app center + Run.ran_by + Issue.assignee_user_id + failure→issue notify.
- **Later**: scheduled auto-run, auto-scoped re-run of affected cases on fix, daily
  digest, overdue SLA/escalation, IM (Feishu/DingTalk), rotation / multiple runners.

## Migration
One alembic revision: create `test_suite` + `notification`; add `run.suite_id/ran_by_user_id/trigger`;
add `issue.assignee_user_id`.
