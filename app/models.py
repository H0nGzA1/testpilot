"""ORM models: Project -> TestCase -> RunResult >- Run.

Mirrors the sample-pool -> run -> result shape (see design doc §5.3):
TestCase is the reusable pool, Run is one batch execution, RunResult is one
row per (run, case).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # GitLab project this project's issues sync with (numeric id or "group/path"); the
    # access token lives in an encrypted Credential (type="gitlab_token").
    gitlab_project: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # Feishu group chat bound to this project: the bot routes runs/pushes results
    # here, and problems raised in this chat attach to this project (no LLM guess).
    feishu_chat_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    # Feishu Bitable (多维表格) this project mirrors its feedback into (one table
    # per project). Parsed from the pasted base URL: app_token + table_id.
    feishu_bitable_app_token: Mapped[str | None] = mapped_column(String(120), nullable=True)
    feishu_bitable_table_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # per-project run tuning; None => fall back to the server defaults
    case_timeout_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    case_max_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # the project's role vocabulary for multi-account auth (e.g. ["requester","approver"])
    roles: Mapped[list] = mapped_column(JSON, default=list)
    # storage_state JSON for logged-in sessions; encrypt before persisting in prod
    login_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Environment(Base):
    """A target environment for a project (dev/test/prod): its own base_url and accounts.
    A run picks an environment; base_url + (env,role)->account resolve from it."""

    __tablename__ = "environment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TestCase(Base):
    __tablename__ = "test_case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    # readable id (e.g. TC-001), auto-assigned per project on create
    case_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    module: Mapped[str | None] = mapped_column(String(200), nullable=True)  # section / grouping
    priority: Mapped[str] = mapped_column(String(10), default="P2")  # P0|P1|P2|P3
    type: Mapped[str] = mapped_column(
        String(20), default="functional"
    )  # functional|smoke|regression|acceptance|negative
    status: Mapped[str] = mapped_column(String(20), default="active")  # draft|active|deprecated
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # role this case executes as (multi-account auth); null => project default account
    role: Mapped[str | None] = mapped_column(String(60), nullable=True)
    references: Mapped[str] = mapped_column(Text, default="")  # linked requirements / tickets
    preconditions: Mapped[str] = mapped_column(Text, default="")
    # the natural-language task the browser agent actually executes
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # structured steps kept as human documentation: [{"action": str, "expected": str}]
    steps: Mapped[list] = mapped_column(JSON, default=list)
    test_data: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # included in "run all enabled"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Run(Base):
    __tablename__ = "run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    case_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending|running|completed|failed|cancelled
    concurrency: Mapped[int] = mapped_column(Integer, default=2)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # suite this run belongs to (nullable — ad-hoc runs have none), who actually ran it,
    # and how it was triggered.
    suite_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ran_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual | suite
    environment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # target env
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TestSuite(Base):
    """A named, reusable selection of test cases with an owner and a default runner.
    Runs are executions of a suite; a suite carries the accountability + reminder cadence."""

    __tablename__ = "test_suite"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    selection_mode: Mapped[str] = mapped_column(String(10), default="cases")  # cases | tags
    case_ids: Mapped[list] = mapped_column(JSON, default=list)
    tag_filter: Mapped[list] = mapped_column(JSON, default=list)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    runner_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    cadence: Mapped[str] = mapped_column(
        String(10), default="none"
    )  # none|daily|weekly|biweekly|monthly
    environment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # default env
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Notification(Base):
    """An in-app notification for a user; `emailed` records whether the same event was
    also sent by email (so a resend/backfill doesn't double-mail)."""

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False, index=True)
    # assigned|reminder_due|reminder_overdue|run_done|issue_assigned|issue_fixed|verified
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)  # in-app route
    suite_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class Issue(Base):
    """A bug/issue tracked on the Kanban board, usually opened from a failed result."""

    __tablename__ = "issue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open|in_progress|fixed|verified|closed
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # low|medium|high|critical
    assignee: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )  # legacy display/GitLab
    assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    # provenance: the failing case/run/result this issue came from (nullable, no FK so
    # deleting a case/run doesn't cascade the issue away)
    case_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # GitLab sync state: iid within the mapped GitLab project, a snapshot of that project
    # ref, the last time we reconciled, and a hash of the last-synced field set (so the
    # poller can tell whether the GitLab side actually changed).
    gitlab_iid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gitlab_project: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # Row id in the project's Feishu Bitable defect table (all issues mirror there).
    bitable_record_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class IssueComment(Base):
    __tablename__ = "issue_comment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issue.id"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # set when this comment originated from (or was mirrored to) a GitLab note — dedupes
    # the poller so a pulled note isn't pushed back and vice-versa.
    gitlab_note_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FeedbackItem(Base):
    """A problem/question raised in a Feishu chat, collected by the bot.

    Every recorded message lands here first; bug/feature items are then promoted
    to an ``Issue`` (see app.feishu) with ``issue_id`` back-linking the promotion.
    ``feishu_message_id`` is unique so Feishu retries can't double-record.
    """

    __tablename__ = "feedback_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(20), default="feishu")
    feishu_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    chat_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    chat_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # group/p2p
    sender_id: Mapped[str | None] = mapped_column(String(120), nullable=True)  # open_id
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(400), nullable=True)
    category: Mapped[str] = mapped_column(String(20), default="other")  # bug/question/feature/other
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # low/medium/high/critical

    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/resolved/ignored

    # Auto-identified project + the Issue it was promoted into (both nullable).
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    issue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Record id in the project's Feishu Bitable (for status write-back). Null until synced.
    bitable_record_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Credential(Base):
    """A stored, encrypted login for a project's app-under-test.

    type=storage_state -> `secret` is an encrypted storage_state JSON (a captured,
      expiring browser session).
    type=password -> `secret` is an encrypted password for `username` (a dedicated
      robot/test account used for self-login).
    `secret` is always ciphertext (see app.crypto); it is never returned by the API.
    """

    __tablename__ = "credential"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # storage_state | password
    # role this account plays (multi-account auth); null = general/default account
    role: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # environment this account belongs to (null = usable in any environment)
    environment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    secret: Mapped[str] = mapped_column(Text, nullable=False)  # ciphertext
    # captured, reusable session bundle (encrypted JSON) for a password account, so cases
    # restore it instead of prompt-logging in every time. Captured on first use
    # (single-flight); re-captured reactively on auth failure (P3). Null until first capture.
    session_bundle: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # account health: flipped false when a run using it fails to log in; recover by a
    # manual re-check (server re-login) or a passing run.
    healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RunResult(Base):
    __tablename__ = "run_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"), nullable=False, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("test_case.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="error")  # passed|failed|error
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    flaky: Mapped[bool] = mapped_column(Boolean, default=False)  # passed only after a retry
    video_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    trace_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    steps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # per-step LLM diagnostics: [{i, action, thought, result, error, screenshot}]
    diagnostics: Mapped[list | None] = mapped_column(JSON, nullable=True)
    judge_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # which account/role this case actually ran as (multi-account audit), e.g. "approver · 主管A"
    account_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Heartbeat, not bookkeeping: a running case rewrites `diagnostics` after every browser
    # step, so this is the last sign of life from the worker driving it. That is what lets
    # reconcile_stale_runs tell a slow case from a case whose worker died.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ---- accounts / RBAC (Phase 1: tables only; enforcement flag-gated) ----
class User(Base):
    __tablename__ = "app_user"  # "user" is reserved in Postgres

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)  # None until set
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # system admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # NULL = has never been through (or dismissed) the guided first-run flow, so it
    # opens on their next sign-in. Existing rows are NULL, which is deliberate:
    # everyone sees it once.
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectMember(Base):
    __tablename__ = "project_member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # owner|editor|viewer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Invite(Base):
    __tablename__ = "invite"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # optional project this invite grants membership to, with a role
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_role: Mapped[str] = mapped_column(String(20), default="editor")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # invite as system admin
    invited_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AppSetting(Base):
    """Admin-managed system settings (e.g. the global GitLab token). Values that are
    secret are stored encrypted (see app.crypto); `secret` marks those rows."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
