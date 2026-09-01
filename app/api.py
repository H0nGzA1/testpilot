"""REST + SSE API. Thin layer over models/engine — no business logic here beyond
project scoping and kicking off runs."""

from __future__ import annotations

import asyncio
import csv
import io
import re
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import delete, func, select
from sse_starlette.sse import EventSourceResponse

from app import auth, excel, feishu, feishu_notify, mailer, notify
from app.celery_app import enqueue_push
from app.config import get_settings
from app.crypto import decrypt, encrypt, secret_configured
from app.gitlab_client import GitLabClient
from app.gitlab_sync import resolve_token
from app.db import db_session
from app.engine import run_suite
from app.models import (
    Credential,
    Environment,
    FeedbackItem,
    Invite,
    Issue,
    IssueComment,
    Notification,
    Project,
    ProjectMember,
    Run,
    RunResult,
    TestCase,
    TestSuite,
    User,
)
from app.schemas import (
    CredentialCaptureIn,
    CredentialIn,
    EnvironmentIn,
    EnvironmentPatch,
    FeishuSettingsIn,
    GitLabConfigIn,
    GitlabTokenIn,
    InviteAcceptIn,
    InviteIn,
    IssueCommentIn,
    IssueIn,
    IssuePatch,
    LoginIn,
    MemberIn,
    MemberPatch,
    ProjectIn,
    ProjectPatch,
    RolesIn,
    RunIn,
    RunPatch,
    SuiteAssignIn,
    SuiteIn,
    SuitePatch,
    TestCaseIn,
    TestCasePatch,
    UserPatch,
)

# cadence -> timedelta for computing a suite's next due date (None = no reminders)
_CADENCE = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "biweekly": timedelta(weeks=2),
    "monthly": timedelta(days=30),
}


def _next_due(cadence: str, frm: datetime | None = None) -> datetime | None:
    delta = _CADENCE.get(cadence)
    if delta is None:
        return None
    return (frm or datetime.now(UTC)) + delta


# public routes (login / invite / config) — no login gate
public = APIRouter(prefix="/api")
# everything else requires login when auth_enabled (require_user is a no-op otherwise)
router = APIRouter(prefix="/api", dependencies=[Depends(auth.require_user)])

# keep strong refs to background run tasks so they aren't garbage-collected mid-run
_TASKS: set[asyncio.Task] = set()

ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}


async def _project_access(request: Request, pid: int, min_role: str) -> str:
    """Resolve the caller's effective role on a project and enforce a minimum.
    Admins (and everyone, while auth is disabled) get 'owner'. Raises 403/404."""
    from app.models import ProjectMember

    settings = get_settings()
    if not settings.auth_enabled:
        return "owner"
    user = await auth.current_user(request)
    if user is None:
        raise HTTPException(401, "authentication required")
    # shared workspace: any logged-in user has full access (login gate only, no RBAC)
    if user.is_admin or settings.shared_workspace:
        return "owner"
    async with db_session() as s:
        m = (
            (
                await s.execute(
                    select(ProjectMember).where(
                        ProjectMember.project_id == pid, ProjectMember.user_id == user.id
                    )
                )
            )
            .scalars()
            .first()
        )
    role = m.role if m else None
    if role is None or ROLE_RANK.get(role, 0) < ROLE_RANK[min_role]:
        raise HTTPException(403, f"requires {min_role} on this project")
    return role


# ---- auth ----
def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _expired(dt: datetime | None) -> bool:
    """tz-safe expiry check (SQLite hands back naive datetimes; treat them as UTC)."""
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt < datetime.now(UTC)


def _user(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "is_admin": u.is_admin,
        "onboarded_at": _iso(u.onboarded_at),
    }


@public.get("/config")
async def public_config() -> dict:
    s = get_settings()
    return {
        "auth_enabled": s.auth_enabled,
        "shared_workspace": s.shared_workspace,
        "public_base_url": s.public_base_url,
    }


@public.post("/auth/login")
async def login(body: LoginIn, response: Response) -> dict:
    async with db_session() as s:
        u = (
            (await s.execute(select(User).where(User.email == body.email.strip().lower())))
            .scalars()
            .first()
        )
        if u is None or not u.is_active or not auth.verify_password(body.password, u.password_hash):
            raise HTTPException(401, "invalid email or password")
        u.last_login_at = datetime.now(UTC)
        token = auth.create_session_token(u.id)
        payload = _user(u)
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=get_settings().jwt_ttl_hours * 3600,
    )
    return payload


@public.post("/auth/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}


@public.get("/auth/me")
async def me(request: Request) -> dict | None:
    u = await auth.current_user(request)
    return _user(u) if u else None


@public.post("/auth/onboarded")
async def set_onboarded(request: Request) -> dict:
    """Mark the guided first-run flow as seen (finished OR skipped — either way we
    stop opening it). No-op without a session, e.g. an auth-disabled instance, where
    the frontend keeps the flag in localStorage instead."""
    u = await auth.current_user(request)
    if u is None:
        return {"onboarded_at": None}
    async with db_session() as s:
        row = await s.get(User, u.id)
        if row is None:
            return {"onboarded_at": None}
        if row.onboarded_at is None:
            row.onboarded_at = datetime.now(UTC)
        return {"onboarded_at": _iso(row.onboarded_at)}


# ---- admin: users + invites ----
@router.get("/admin/users", dependencies=[Depends(auth.require_admin)])
async def list_users() -> list[dict]:
    async with db_session() as s:
        rows = (await s.execute(select(User).order_by(User.id))).scalars().all()
        return [
            {**_user(u), "is_active": u.is_active, "last_login_at": _iso(u.last_login_at)}
            for u in rows
        ]


@router.post("/admin/users/invite", dependencies=[Depends(auth.require_admin)])
async def invite_user(body: InviteIn, request: Request) -> dict:
    email = body.email.strip().lower()
    inviter = await auth.current_user(request)
    async with db_session() as s:
        exists = (
            await s.execute(select(func.count()).select_from(User).where(User.email == email))
        ).scalar_one()
        if exists:
            raise HTTPException(400, "a user with this email already exists")
        token = auth.new_invite_token()
        s.add(
            Invite(
                email=email,
                token=token,
                project_id=body.project_id,
                project_role=body.project_role,
                is_admin=body.is_admin,
                invited_by=inviter.id if inviter else None,
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
    base = get_settings().public_base_url.rstrip("/")
    link = f"{base}/invite/{token}" if base else f"/invite/{token}"
    subject, mailbody = mailer.invite_email_body(inviter.email if inviter else "TestPilot", link)
    sent = await mailer.send_email(email, subject, mailbody)
    return {"email": email, "link": link, "emailed": sent}


@router.patch("/admin/users/{uid}", dependencies=[Depends(auth.require_admin)])
async def update_user(uid: int, body: UserPatch) -> dict:
    async with db_session() as s:
        u = await s.get(User, uid)
        if u is None:
            raise HTTPException(404, "user not found")
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(u, k, v)
        await s.flush()
        return {**_user(u), "is_active": u.is_active}


# ---- admin: system settings ----
def _feishu_status(cfg: dict) -> dict:
    """Public-safe view of the Feishu config (secrets shown only as *_set booleans)."""
    return {
        "app_id": cfg["app_id"],
        "app_secret_set": bool(cfg["app_secret"]),
        "verification_token_set": bool(cfg["verification_token"]),
        "api_base": cfg["api_base"],
        "auto_answer_detected": cfg["auto_answer_detected"],
    }


@router.get("/admin/settings", dependencies=[Depends(auth.require_admin)])
async def get_admin_settings() -> dict:
    from app.settings_store import GITLAB_TOKEN_KEY, has_setting

    async with db_session() as s:
        token_set = await has_setting(s, GITLAB_TOKEN_KEY)
        feishu_cfg = await feishu.resolve_config(s)
    return {
        "gitlab_token_set": token_set or bool(get_settings().gitlab_token),
        "feishu": _feishu_status(feishu_cfg),
    }


@router.put("/admin/settings/gitlab-token", dependencies=[Depends(auth.require_admin)])
async def set_admin_gitlab_token(body: GitlabTokenIn) -> dict:
    from app.settings_store import GITLAB_TOKEN_KEY, set_setting

    if body.token and not secret_configured():
        raise HTTPException(400, "TESTPILOT_SECRET_KEY not configured — cannot store token")
    async with db_session() as s:
        await set_setting(s, GITLAB_TOKEN_KEY, body.token.strip(), secret=True)
    return {"gitlab_token_set": bool(body.token.strip())}


@router.put("/admin/settings/feishu", dependencies=[Depends(auth.require_admin)])
async def set_admin_feishu(body: FeishuSettingsIn) -> dict:
    from app.settings_store import set_setting

    async with db_session() as s:
        if body.app_id is not None:
            await set_setting(s, "feishu_app_id", body.app_id.strip(), secret=False)
        if body.api_base is not None:
            await set_setting(s, "feishu_api_base", body.api_base.strip(), secret=False)
        if body.auto_answer_detected is not None:
            await set_setting(
                s,
                "feishu_auto_answer_detected",
                "true" if body.auto_answer_detected else "false",
                secret=False,
            )
        # Secrets: only overwrite when a non-empty value is provided (blank keeps existing).
        for value, key in (
            (body.app_secret, "feishu_app_secret"),
            (body.verification_token, "feishu_verification_token"),
        ):
            if value:
                if not secret_configured():
                    raise HTTPException(
                        400, "TESTPILOT_SECRET_KEY not configured — cannot store secret"
                    )
                await set_setting(s, key, value.strip(), secret=True)
        cfg = await feishu.resolve_config(s)
    return _feishu_status(cfg)


# ---- invite acceptance (public) ----
@public.get("/invite/{token}")
async def get_invite(token: str) -> dict:
    async with db_session() as s:
        inv = (await s.execute(select(Invite).where(Invite.token == token))).scalars().first()
        if inv is None or inv.accepted_at is not None:
            raise HTTPException(404, "invite not found or already used")
        if _expired(inv.expires_at):
            raise HTTPException(410, "invite expired")
        return {"email": inv.email, "is_admin": inv.is_admin, "project_id": inv.project_id}


@public.post("/invite/{token}/accept")
async def accept_invite(token: str, body: InviteAcceptIn, response: Response) -> dict:
    async with db_session() as s:
        inv = (await s.execute(select(Invite).where(Invite.token == token))).scalars().first()
        if inv is None or inv.accepted_at is not None:
            raise HTTPException(404, "invite not found or already used")
        if _expired(inv.expires_at):
            raise HTTPException(410, "invite expired")
        u = User(
            email=inv.email,
            name=body.name or inv.email.split("@")[0],
            password_hash=auth.hash_password(body.password),
            is_admin=inv.is_admin,
            is_active=True,
        )
        s.add(u)
        await s.flush()
        if inv.project_id is not None:
            s.add(ProjectMember(project_id=inv.project_id, user_id=u.id, role=inv.project_role))
        inv.accepted_at = datetime.now(UTC)
        token_str = auth.create_session_token(u.id)
        payload = _user(u)
    response.set_cookie(
        auth.COOKIE_NAME,
        token_str,
        httponly=True,
        samesite="lax",
        max_age=get_settings().jwt_ttl_hours * 3600,
    )
    return payload


# ---- project members ----
@router.get("/projects/{pid}/members")
async def list_members(pid: int, request: Request) -> list[dict]:
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        rows = (
            await s.execute(
                select(ProjectMember, User)
                .join(User, User.id == ProjectMember.user_id)
                .where(ProjectMember.project_id == pid)
                .order_by(ProjectMember.id)
            )
        ).all()
        return [
            {"user_id": u.id, "email": u.email, "name": u.name, "role": m.role} for m, u in rows
        ]


@router.get("/projects/{pid}/assignable-users")
async def assignable_users(pid: int, request: Request, q: str = "") -> list[dict]:
    """Active users (with an account) not already members — powers the member search picker."""
    await _project_access(request, pid, "owner")
    async with db_session() as s:
        member_ids = (
            (await s.execute(select(ProjectMember.user_id).where(ProjectMember.project_id == pid)))
            .scalars()
            .all()
        )
        query = select(User).where(User.is_active.is_(True))
        ql = q.strip().lower()
        if ql:
            like = f"%{ql}%"
            query = query.where(
                func.lower(User.email).like(like)
                | func.lower(func.coalesce(User.name, "")).like(like)
            )
        if member_ids:
            query = query.where(User.id.not_in(member_ids))
        rows = (await s.execute(query.order_by(User.email).limit(10))).scalars().all()
        return [{"id": u.id, "email": u.email, "name": u.name} for u in rows]


@router.post("/projects/{pid}/members")
async def add_member(pid: int, body: MemberIn, request: Request) -> dict:
    await _project_access(request, pid, "owner")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        u = (
            (await s.execute(select(User).where(User.email == body.email.strip().lower())))
            .scalars()
            .first()
        )
        if u is None:
            raise HTTPException(404, "no user with that email (invite them first)")
        existing = (
            (
                await s.execute(
                    select(ProjectMember).where(
                        ProjectMember.project_id == pid, ProjectMember.user_id == u.id
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing:
            existing.role = body.role
        else:
            s.add(ProjectMember(project_id=pid, user_id=u.id, role=body.role))
        return {"user_id": u.id, "email": u.email, "name": u.name, "role": body.role}


@router.patch("/projects/{pid}/members/{uid}")
async def update_member(pid: int, uid: int, body: MemberPatch, request: Request) -> dict:
    await _project_access(request, pid, "owner")
    async with db_session() as s:
        m = (
            (
                await s.execute(
                    select(ProjectMember).where(
                        ProjectMember.project_id == pid, ProjectMember.user_id == uid
                    )
                )
            )
            .scalars()
            .first()
        )
        if m is None:
            raise HTTPException(404, "member not found")
        m.role = body.role
        return {"user_id": uid, "role": body.role}


@router.delete("/projects/{pid}/members/{uid}")
async def remove_member(pid: int, uid: int, request: Request) -> dict:
    await _project_access(request, pid, "owner")
    async with db_session() as s:
        m = (
            (
                await s.execute(
                    select(ProjectMember).where(
                        ProjectMember.project_id == pid, ProjectMember.user_id == uid
                    )
                )
            )
            .scalars()
            .first()
        )
        if m is not None:
            await s.delete(m)
    return {"removed": uid}


def _project(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "base_url": p.base_url,
        "has_login_state": bool(p.login_state),
        "gitlab_project": p.gitlab_project,
        "case_timeout_s": p.case_timeout_s,
        "case_max_steps": p.case_max_steps,
        "run_concurrency": p.run_concurrency,
        "roles": p.roles or [],
        "feishu_chat_id": p.feishu_chat_id,
        "feishu_bitable_bound": bool(p.feishu_bitable_app_token and p.feishu_bitable_table_id),
    }


def _gitlab_web_url(project_ref: str | None, iid: int | None) -> str | None:
    """Best-effort browser URL for a synced GitLab issue (derives web host from the API base)."""
    if not project_ref or not iid:
        return None
    host = get_settings().gitlab_base_url.split("/api/v4", 1)[0].rstrip("/")
    return f"{host}/{project_ref}/-/issues/{iid}"


class LastResult(NamedTuple):
    """A case's most recent verdict — status, the run it came from, when it ran."""

    status: str
    run_id: int
    at: datetime | None


def _case(c: TestCase, last: LastResult | None = None) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        # How this case last did. The cases table shows 通过/失败 + when + a link to that
        # report, so "is this case OK?" is answerable without opening every run.
        "last_status": last.status if last else None,  # passed|failed|error, None = never run
        "last_run_id": last.run_id if last else None,
        "last_run_at": _iso(last.at) if last else None,
        "case_key": c.case_key,
        "name": c.name,
        "module": c.module,
        "priority": c.priority,
        "type": c.type,
        "status": c.status,
        "owner": c.owner,
        "role": c.role,
        "references": c.references or "",
        "preconditions": c.preconditions or "",
        "prompt": c.prompt,
        "steps": c.steps or [],
        "test_data": c.test_data or "",
        "expected": c.expected,
        "start_url": c.start_url,
        "tags": c.tags or [],
        "enabled": c.enabled,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _run(r: Run) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "name": r.name,
        "status": r.status,
        "case_ids": r.case_ids or [],
        "concurrency": r.concurrency,
        "total_count": r.total_count,
        "processed_count": r.processed_count,
        "passed_count": r.passed_count,
        "summary": r.summary,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "created_by": r.created_by,
        "suite_id": r.suite_id,
        "ran_by_user_id": r.ran_by_user_id,
        "trigger": r.trigger,
        "environment_id": r.environment_id,
    }


def _result(x: RunResult) -> dict:
    return {
        "id": x.id,
        "run_id": x.run_id,
        "case_id": x.case_id,
        "status": x.status,
        "attempts": x.attempts,
        "flaky": x.flaky,
        "video_url": x.video_url,
        "trace_url": x.trace_url,
        "steps": x.steps or [],
        "diagnostics": x.diagnostics or [],
        "judge_reason": x.judge_reason,
        "final_answer": x.final_answer,
        "account_label": x.account_label,
        "latency_ms": x.latency_ms,
        "error": x.error,
    }


# ---- projects ----
@router.get("/projects")
async def list_projects(request: Request) -> list[dict]:
    async with db_session() as s:
        q = select(Project).order_by(Project.id.desc())
        # non-admins see only projects they're a member of (unless shared_workspace)
        settings = get_settings()
        user = await auth.current_user(request) if settings.auth_enabled else None
        if user is not None and not user.is_admin and not settings.shared_workspace:
            member_ids = (
                (
                    await s.execute(
                        select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
                    )
                )
                .scalars()
                .all()
            )
            if not member_ids:
                return []
            q = q.where(Project.id.in_(member_ids))
        rows = (await s.execute(q)).scalars().all()
        out = []
        for p in rows:
            d = _project(p)
            if not d["has_login_state"]:
                d["has_login_state"] = bool(
                    (
                        await s.execute(
                            select(func.count())
                            .select_from(Credential)
                            .where(
                                Credential.project_id == p.id,
                                Credential.is_active == True,
                                Credential.type == "storage_state",
                            )
                        )
                    ).scalar_one()
                )
            d["case_count"] = (
                await s.execute(
                    select(func.count()).select_from(TestCase).where(TestCase.project_id == p.id)
                )
            ).scalar_one()
            last = (
                await s.execute(
                    select(Run).where(Run.project_id == p.id).order_by(Run.id.desc()).limit(1)
                )
            ).scalar_one_or_none()
            d["last_run"] = (
                {
                    "id": last.id,
                    "status": last.status,
                    "pass_rate": (last.summary or {}).get("pass_rate") if last.summary else None,
                    "finished_at": last.finished_at.isoformat() if last.finished_at else None,
                }
                if last
                else None
            )
            out.append(d)
        return out


@router.post("/projects")
async def create_project(body: ProjectIn, request: Request) -> dict:
    async with db_session() as s:
        p = Project(name=body.name, base_url=body.base_url, login_state=body.login_state)
        s.add(p)
        await s.flush()
        # the creator owns the project (so it's visible + manageable under RBAC)
        user = await auth.current_user(request)
        if user is not None:
            s.add(ProjectMember(project_id=p.id, user_id=user.id, role="owner"))
        return _project(p)


@router.put("/projects/{pid}")
async def update_project(pid: int, body: ProjectPatch, request: Request) -> dict:
    await _project_access(request, pid, "owner")
    async with db_session() as s:
        p = await _get_project_or_404(s, pid)
        data = body.model_dump(exclude_none=True)
        if "feishu_bitable_url" in data:
            from app.feishu_bitable import parse_bitable_url

            app_token, table_id = parse_bitable_url(data.pop("feishu_bitable_url"))
            p.feishu_bitable_app_token = app_token
            p.feishu_bitable_table_id = table_id
        for k, v in data.items():
            setattr(p, k, v)
        await s.flush()
        return _project(p)


@router.get("/projects/{pid}/roles")
async def get_roles(pid: int, request: Request) -> dict:
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        p = await _get_project_or_404(s, pid)
        return {"roles": p.roles or []}


@router.put("/projects/{pid}/roles")
async def set_roles(pid: int, body: RolesIn, request: Request) -> dict:
    await _project_access(request, pid, "editor")
    async with db_session() as s:
        p = await _get_project_or_404(s, pid)
        # keep order, drop blanks/dupes
        seen: list[str] = []
        for r in body.roles:
            r = r.strip()
            if r and r not in seen:
                seen.append(r)
        p.roles = seen
        return {"roles": seen}


def _env(e: Environment) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "name": e.name,
        "base_url": e.base_url,
        "is_default": e.is_default,
    }


async def _default_env_id(s, pid: int) -> int | None:
    """The project's default environment. A run without an explicit env must fall back to
    it — base_url and (env, role)->account both live on the environment, so env=None means
    env-bound accounts never match ("角色「x」没有可用账号")."""
    e = (
        (
            await s.execute(
                select(Environment)
                .where(Environment.project_id == pid, Environment.is_default == True)
                .order_by(Environment.id)
            )
        )
        .scalars()
        .first()
    )
    return e.id if e else None


@router.get("/projects/{pid}/environments")
async def list_environments(pid: int, request: Request) -> list[dict]:
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        rows = (
            (
                await s.execute(
                    select(Environment)
                    .where(Environment.project_id == pid)
                    .order_by(Environment.id)
                )
            )
            .scalars()
            .all()
        )
        return [_env(e) for e in rows]


@router.post("/projects/{pid}/environments")
async def create_environment(pid: int, body: EnvironmentIn, request: Request) -> dict:
    await _project_access(request, pid, "editor")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        if body.is_default:
            for e in (
                (await s.execute(select(Environment).where(Environment.project_id == pid)))
                .scalars()
                .all()
            ):
                e.is_default = False
        e = Environment(
            project_id=pid, name=body.name, base_url=body.base_url, is_default=body.is_default
        )
        s.add(e)
        await s.flush()
        return _env(e)


@router.put("/environments/{eid}")
async def update_environment(eid: int, body: EnvironmentPatch, request: Request) -> dict:
    async with db_session() as s:
        e = await s.get(Environment, eid)
        if e is None:
            raise HTTPException(404, "environment not found")
        await _project_access(request, e.project_id, "editor")
        data = body.model_dump(exclude_none=True)
        if data.get("is_default"):
            for other in (
                (await s.execute(select(Environment).where(Environment.project_id == e.project_id)))
                .scalars()
                .all()
            ):
                other.is_default = False
        for k, v in data.items():
            setattr(e, k, v)
        return _env(e)


@router.delete("/environments/{eid}")
async def delete_environment(eid: int, request: Request) -> dict:
    async with db_session() as s:
        e = await s.get(Environment, eid)
        if e is None:
            raise HTTPException(404, "environment not found")
        await _project_access(request, e.project_id, "editor")
        await s.delete(e)
        return {"deleted": eid}


@router.delete("/projects/{pid}")
async def delete_project(pid: int, request: Request) -> dict:
    """Delete a project and everything under it. Owner-only, irreversible."""
    await _project_access(request, pid, "owner")
    async with db_session() as s:
        p = await _get_project_or_404(s, pid)
        run_ids = (await s.execute(select(Run.id).where(Run.project_id == pid))).scalars().all()
        issue_ids = (
            (await s.execute(select(Issue.id).where(Issue.project_id == pid))).scalars().all()
        )
        if run_ids:
            await s.execute(delete(RunResult).where(RunResult.run_id.in_(run_ids)))
        if issue_ids:
            await s.execute(delete(IssueComment).where(IssueComment.issue_id.in_(issue_ids)))
        for model in (TestCase, Run, Issue, Credential, ProjectMember, TestSuite, Environment):
            await s.execute(delete(model).where(model.project_id == pid))
        await s.delete(p)
        return {"deleted": pid}


@router.get("/projects/{pid}/gitlab")
async def get_gitlab_config(pid: int, request: Request) -> dict:
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        p = await _get_project_or_404(s, pid)
        token = (
            (
                await s.execute(
                    select(Credential).where(
                        Credential.project_id == pid,
                        Credential.type == "gitlab_token",
                        Credential.is_active == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .first()
        )
        has_global = bool(get_settings().gitlab_token)
        source = "project" if token is not None else ("global" if has_global else None)
        return {
            "gitlab_project": p.gitlab_project,
            "has_token": token is not None or has_global,
            "token_source": source,
            "sync_enabled": bool(get_settings().redis_url),
        }


@router.get("/projects/{pid}/gitlab/projects")
async def list_gitlab_projects(pid: int, request: Request) -> list[dict]:
    """GitLab projects the token can access — populates the settings dropdown. Uses the
    project's token or the server-wide GITLAB_TOKEN; empty list if neither is set."""
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        token = await resolve_token(s, pid)
    if not token:
        return []
    client = GitLabClient(token, project="")
    try:
        items = await client.list_accessible_projects()
    except Exception as e:
        raise HTTPException(502, f"could not list GitLab projects: {e}") from e
    return [
        {"id": p["id"], "path": p["path_with_namespace"], "name": p.get("name")}
        for p in items
        if p.get("path_with_namespace")
    ]


@router.put("/projects/{pid}/gitlab")
async def set_gitlab_config(pid: int, body: GitLabConfigIn, request: Request) -> dict:
    await _project_access(request, pid, "owner")
    """Map this project to a GitLab project and (optionally) store an encrypted token.
    An empty gitlab_project unlinks the project; the token is write-only (never returned)."""
    async with db_session() as s:
        p = await _get_project_or_404(s, pid)
        p.gitlab_project = body.gitlab_project or None
        if body.token:
            if not secret_configured():
                raise HTTPException(
                    400, "TESTPILOT_SECRET_KEY not configured — token storage disabled"
                )
            for c in (
                (
                    await s.execute(
                        select(Credential).where(
                            Credential.project_id == pid, Credential.type == "gitlab_token"
                        )
                    )
                )
                .scalars()
                .all()
            ):
                c.is_active = False
            s.add(
                Credential(
                    project_id=pid,
                    type="gitlab_token",
                    label="GitLab token",
                    secret=encrypt(body.token),
                    is_active=True,
                )
            )
        await s.flush()
        project_token = (
            await s.execute(
                select(func.count())
                .select_from(Credential)
                .where(
                    Credential.project_id == pid,
                    Credential.type == "gitlab_token",
                    Credential.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one() > 0
        has_global = bool(get_settings().gitlab_token)
        source = "project" if project_token else ("global" if has_global else None)
        return {
            "gitlab_project": p.gitlab_project,
            "has_token": project_token or has_global,
            "token_source": source,
            "sync_enabled": bool(get_settings().redis_url),
        }


@router.get("/projects/{pid}/stats")
async def project_stats(pid: int, request: Request) -> dict:
    await _project_access(request, pid, "viewer")
    """Aggregates for the Overview dashboard: counts, pass-rate trend, last-run
    latency/flaky, and the cases that fail most across this project's runs."""
    async with db_session() as s:
        project = await _get_project_or_404(s, pid)

        case_count = (
            await s.execute(
                select(func.count()).select_from(TestCase).where(TestCase.project_id == pid)
            )
        ).scalar_one()
        enabled_count = (
            await s.execute(
                select(func.count())
                .select_from(TestCase)
                .where(TestCase.project_id == pid, TestCase.enabled == True)
            )
        ).scalar_one()

        # Setup-checklist inputs (Overview). The checklist is derived from live state,
        # never from a stored "onboarding done" flag — so it can't drift.
        cred_rows = (
            (await s.execute(select(Credential.healthy).where(Credential.project_id == pid)))
            .scalars()
            .all()
        )
        issue_count = (
            await s.execute(select(func.count()).select_from(Issue).where(Issue.project_id == pid))
        ).scalar_one()

        runs = (
            (await s.execute(select(Run).where(Run.project_id == pid).order_by(Run.id)))
            .scalars()
            .all()
        )
        completed = [r for r in runs if r.status in ("completed", "cancelled") and r.summary]
        trend = [
            {
                "run_id": r.id,
                "name": r.name,
                "pass_rate": (r.summary or {}).get("pass_rate", 0.0),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in completed[-10:]
        ]
        last = runs[-1] if runs else None
        last_summary = (last.summary or {}) if last else {}

        # cases that fail most across all runs in this project
        fail_rows = (
            await s.execute(
                select(RunResult.case_id, func.count().label("n"))
                .join(Run, RunResult.run_id == Run.id)
                .where(Run.project_id == pid, RunResult.status.in_(("failed", "error")))
                .group_by(RunResult.case_id)
                .order_by(func.count().desc())
                .limit(5)
            )
        ).all()
        names = (
            {
                c.id: c.name
                for c in (
                    await s.execute(
                        select(TestCase).where(TestCase.id.in_([r.case_id for r in fail_rows]))
                    )
                ).scalars()
            }
            if fail_rows
            else {}
        )
        top_failing = [
            {"case_id": r.case_id, "name": names.get(r.case_id, f"#{r.case_id}"), "fail_count": r.n}
            for r in fail_rows
        ]

        return {
            "base_url": project.base_url,
            "has_credential": bool(cred_rows),
            "has_healthy_credential": any(cred_rows),
            "issue_count": issue_count,
            "case_count": case_count,
            "enabled_count": enabled_count,
            "run_count": len(runs),
            "last_run": _run(last) if last else None,
            "trend": trend,
            "last_pass_rate": last_summary.get("pass_rate"),
            "last_latency_p50_ms": last_summary.get("latency_p50_ms"),
            "last_flaky": last_summary.get("flaky", 0),
            "top_failing": top_failing,
        }


# ---- test cases ----
async def _get_project_or_404(s, pid: int) -> Project:
    p = await s.get(Project, pid)
    if p is None:
        raise HTTPException(404, "project not found")
    return p


@router.get("/projects/{pid}/testcases")
async def list_cases(pid: int, request: Request) -> list[dict]:
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        rows = (
            (
                await s.execute(
                    select(TestCase).where(TestCase.project_id == pid).order_by(TestCase.id)
                )
            )
            .scalars()
            .all()
        )
        # latest RunResult per case (coverage / pass-rate / compare, and the cases table's
        # "last result" column); one query, newest-first, keep the first row seen per case.
        last: dict[int, LastResult] = {}
        case_ids = [c.id for c in rows]
        if case_ids:
            res_rows = (
                await s.execute(
                    select(
                        RunResult.case_id,
                        RunResult.status,
                        RunResult.run_id,
                        RunResult.created_at,
                    )
                    .where(RunResult.case_id.in_(case_ids))
                    .order_by(RunResult.id.desc())
                )
            ).all()
            for cid, st, run_id, at in res_rows:
                if cid not in last:
                    last[cid] = LastResult(st, run_id, at)
        return [_case(c, last.get(c.id)) for c in rows]


async def _next_case_key(s, pid: int) -> str:
    """Readable per-project id like TC-001 (count-based; not uniqueness-enforced)."""
    n = (
        await s.execute(
            select(func.count()).select_from(TestCase).where(TestCase.project_id == pid)
        )
    ).scalar_one()
    return f"TC-{n + 1:03d}"


@router.post("/projects/{pid}/testcases")
async def create_case(pid: int, body: TestCaseIn, request: Request) -> dict:
    await _project_access(request, pid, "editor")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        data = body.model_dump()
        if not data.get("case_key"):
            data["case_key"] = await _next_case_key(s, pid)
        c = TestCase(project_id=pid, **data)
        s.add(c)
        await s.flush()
        return _case(c)


@router.put("/testcases/{cid}")
async def update_case(cid: int, body: TestCasePatch, request: Request) -> dict:
    async with db_session() as s:
        c = await s.get(TestCase, cid)
        if c is None:
            raise HTTPException(404, "test case not found")
        await _project_access(request, c.project_id, "editor")
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(c, k, v)
        await s.flush()
        return _case(c)


@router.delete("/testcases/{cid}")
async def delete_case(cid: int, request: Request) -> dict:
    async with db_session() as s:
        c = await s.get(TestCase, cid)
        if c is None:
            raise HTTPException(404, "test case not found")
        await _project_access(request, c.project_id, "editor")
        # run_result.case_id is a non-cascading FK — drop the case's historical
        # results first, otherwise the delete violates run_result_case_id_fkey.
        await s.execute(delete(RunResult).where(RunResult.case_id == cid))
        await s.delete(c)
        return {"deleted": cid}


def _cred(c: Credential) -> dict:
    # NOTE: never include `secret` — ciphertext must not leave the server.
    return {
        "id": c.id,
        "project_id": c.project_id,
        "type": c.type,
        "role": c.role,
        "environment_id": c.environment_id,
        "label": c.label,
        "username": c.username,
        "is_active": c.is_active,
        "healthy": c.healthy,
        "last_error": c.last_error,
        "last_checked_at": _iso(c.last_checked_at),
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/projects/{pid}/credentials")
async def list_credentials(pid: int, request: Request) -> list[dict]:
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        await _project_access(request, pid, "viewer")
        rows = (
            (
                await s.execute(
                    select(Credential)
                    # gitlab_token is managed by the GitLab-sync section, not the login list
                    .where(Credential.project_id == pid, Credential.type != "gitlab_token")
                    .order_by(Credential.id.desc())
                )
            )
            .scalars()
            .all()
        )
        return [_cred(c) for c in rows]


@router.post("/projects/{pid}/credentials")
async def create_credential(pid: int, body: CredentialIn, request: Request) -> dict:
    if not secret_configured():
        raise HTTPException(
            400, "TESTPILOT_SECRET_KEY not configured — credential storage disabled"
        )
    if body.type == "password" and not body.username:
        raise HTTPException(400, "username is required for a password credential")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        await _project_access(request, pid, "editor")
        # the default login is a single active storage_state; adding a new one deactivates
        # the previous storage_state only. Role/password accounts coexist (multi-account).
        if body.type == "storage_state":
            existing = (
                (
                    await s.execute(
                        select(Credential).where(
                            Credential.project_id == pid, Credential.type == "storage_state"
                        )
                    )
                )
                .scalars()
                .all()
            )
            for e in existing:
                e.is_active = False
        c = Credential(
            project_id=pid,
            type=body.type,
            role=body.role,
            environment_id=body.environment_id,
            label=body.label or body.type,
            username=body.username,
            secret=encrypt(body.secret),
            is_active=True,
        )
        s.add(c)
        await s.flush()
        return _cred(c)


@router.post("/projects/{pid}/credentials/capture")
async def capture_credential(pid: int, body: CredentialCaptureIn, request: Request) -> dict:
    """Web-only login: server logs into the project's base_url with this account,
    captures the session, and stores it (active) plus the account (for refresh)."""
    if not secret_configured():
        raise HTTPException(
            400, "TESTPILOT_SECRET_KEY not configured — credential storage disabled"
        )
    async with db_session() as s:
        project = await _get_project_or_404(s, pid)
        await _project_access(request, pid, "editor")
        base_url = project.base_url
    if not base_url:
        raise HTTPException(400, "set the project Base URL first")

    from app.executor import capture_session

    try:
        state = await capture_session(base_url, body.username, body.password)
    except Exception as exc:
        raise HTTPException(
            502, f"login capture failed: {type(exc).__name__}: {exc}"[:300]
        ) from exc

    async with db_session() as s:
        existing = (
            (await s.execute(select(Credential).where(Credential.project_id == pid)))
            .scalars()
            .all()
        )
        for e in existing:
            e.is_active = False
        # store the account (inactive, for future refresh) + the captured session (active)
        s.add(
            Credential(
                project_id=pid,
                type="password",
                label=(body.label or "robot account"),
                username=body.username,
                secret=encrypt(body.password),
                is_active=False,
            )
        )
        session_cred = Credential(
            project_id=pid,
            type="storage_state",
            label=(body.label or f"{body.username} session"),
            secret=encrypt(state),
            is_active=True,
        )
        s.add(session_cred)
        await s.flush()
        return _cred(session_cred)


@router.post("/credentials/{cid}/activate")
async def activate_credential(cid: int, request: Request) -> dict:
    async with db_session() as s:
        c = await s.get(Credential, cid)
        if c is None:
            raise HTTPException(404, "credential not found")
        await _project_access(request, c.project_id, "editor")
        others = (
            (await s.execute(select(Credential).where(Credential.project_id == c.project_id)))
            .scalars()
            .all()
        )
        for o in others:
            o.is_active = o.id == cid
        return _cred(c)


@router.post("/credentials/{cid}/recheck")
async def recheck_credential(cid: int, request: Request) -> dict:
    """Re-validate a password account by logging into its environment's base URL, and
    update its health. Only password accounts (they carry the login) can be re-checked."""
    async with db_session() as s:
        c = await s.get(Credential, cid)
        if c is None:
            raise HTTPException(404, "credential not found")
        await _project_access(request, c.project_id, "editor")
        if c.type != "password" or not c.username:
            raise HTTPException(400, "only password accounts can be re-checked")
        project = await s.get(Project, c.project_id)
        base_url = project.base_url if project else None
        if c.environment_id is not None:
            env = await s.get(Environment, c.environment_id)
            if env is not None and env.base_url:
                base_url = env.base_url
        username = c.username
        password = decrypt(c.secret)
    if not base_url:
        raise HTTPException(400, "set the project or environment Base URL first")

    from app.executor import capture_session

    ok = True
    err: str | None = None
    try:
        await capture_session(base_url, username, password)
    except Exception as exc:
        ok = False
        err = f"{type(exc).__name__}: {exc}"[:400]

    async with db_session() as s:
        c = await s.get(Credential, cid)
        if c is None:
            raise HTTPException(404, "credential not found")
        c.healthy = ok
        c.last_error = None if ok else err
        c.last_checked_at = datetime.now(UTC)
        return _cred(c)


@router.delete("/credentials/{cid}")
async def delete_credential(cid: int, request: Request) -> dict:
    async with db_session() as s:
        c = await s.get(Credential, cid)
        if c is None:
            raise HTTPException(404, "credential not found")
        await _project_access(request, c.project_id, "editor")
        await s.delete(c)
        return {"deleted": cid}


@router.get("/testcases/{cid}/results")
async def case_results(cid: int, request: Request) -> list[dict]:
    """This case's outcome across every run it appeared in (newest first)."""
    async with db_session() as s:
        c = await s.get(TestCase, cid)
        if c is None:
            raise HTTPException(404, "test case not found")
        await _project_access(request, c.project_id, "viewer")
        rows = (
            await s.execute(
                select(RunResult, Run)
                .join(Run, RunResult.run_id == Run.id)
                .where(RunResult.case_id == cid)
                .order_by(Run.id.desc())
            )
        ).all()
        return [
            {
                "result_id": rr.id,
                "run_id": run.id,
                "run_name": run.name,
                "status": rr.status,
                "flaky": rr.flaky,
                "latency_ms": rr.latency_ms,
                "judge_reason": rr.judge_reason,
                "video_url": rr.video_url,
                "trace_url": rr.trace_url,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }
            for rr, run in rows
        ]


@router.post("/projects/{pid}/testcases/import")
async def import_cases(pid: int, request: Request, file: UploadFile = File(...)) -> dict:
    """Bulk-import test cases from an .xlsx (the only supported format)."""
    data = await file.read()
    try:
        records = excel.parse_workbook(data)
    except Exception as e:
        raise HTTPException(400, f"could not read Excel file: {e}") from e
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        await _project_access(request, pid, "editor")
        imported = 0
        for rec in records:
            try:
                item = TestCaseIn(**rec)
            except Exception:
                continue  # skip malformed rows rather than failing the whole import
            payload = item.model_dump()
            if not payload.get("case_key"):
                payload["case_key"] = await _next_case_key(s, pid)
            s.add(TestCase(project_id=pid, **payload))
            await s.flush()
            imported += 1
    return {"imported": imported}


@router.get("/projects/{pid}/testcases/export")
async def export_cases(pid: int, request: Request) -> StreamingResponse:
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        await _project_access(request, pid, "viewer")
        rows = (
            (
                await s.execute(
                    select(TestCase).where(TestCase.project_id == pid).order_by(TestCase.id)
                )
            )
            .scalars()
            .all()
        )
    content = excel.build_workbook([_case(c) for c in rows])
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="project-{pid}-testcases.xlsx"'},
    )


@router.get("/projects/{pid}/testcases/template")
async def testcase_template(pid: int) -> StreamingResponse:
    return StreamingResponse(
        iter([excel.template_bytes()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="testpilot-testcase-template.xlsx"'},
    )


# ---- runs ----
async def _launch(run_id: int) -> None:
    """Kick off a run: fan its cases out as Celery case-tasks when Redis is configured
    (worker --concurrency is the global budget), else run in-process (dev/no-broker)."""
    if get_settings().redis_url:
        from app.celery_app import fan_out_run
        from app.engine import prepare_run

        case_ids = await prepare_run(run_id)
        if case_ids:
            fan_out_run(run_id, case_ids)
        return
    task = asyncio.create_task(run_suite(run_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


@router.post("/projects/{pid}/runs")
async def create_run(pid: int, body: RunIn, request: Request) -> dict:
    await _project_access(request, pid, "editor")
    async with db_session() as s:
        proj = await _get_project_or_404(s, pid)
        q = select(TestCase).where(TestCase.project_id == pid, TestCase.enabled == True)
        if body.case_ids:
            q = select(TestCase).where(TestCase.project_id == pid, TestCase.id.in_(body.case_ids))
        cases = (await s.execute(q)).scalars().all()
        if body.tags:
            wanted = set(body.tags)
            cases = [c for c in cases if wanted & set(c.tags or [])]
        if not cases:
            raise HTTPException(400, "no matching test cases")
        # concurrency: explicit request wins, else the project's setting, else default
        concurrency = body.concurrency if body.concurrency != 2 else (proj.run_concurrency or 2)
        run = Run(
            project_id=pid,
            name=body.name,
            case_ids=[c.id for c in cases],
            concurrency=concurrency,
            total_count=len(cases),
            environment_id=body.environment_id or await _default_env_id(s, pid),
        )
        s.add(run)
        await s.flush()
        run_id = run.id
        payload = _run(run)
    await _launch(run_id)
    return payload


@router.get("/projects/{pid}/runs")
async def list_runs(pid: int, request: Request) -> list[dict]:
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        rows = (
            (await s.execute(select(Run).where(Run.project_id == pid).order_by(Run.id.desc())))
            .scalars()
            .all()
        )
        return [_run(r) for r in rows]


@router.get("/runs/{rid}")
async def get_run(rid: int, request: Request) -> dict:
    async with db_session() as s:
        r = await s.get(Run, rid)
        if r is None:
            raise HTTPException(404, "run not found")
        await _project_access(request, r.project_id, "viewer")
        return {**_run(r), "ran_by_label": await _user_label(s, r.ran_by_user_id)}


@router.get("/runs/{rid}/results")
async def get_results(rid: int, request: Request) -> list[dict]:
    async with db_session() as s:
        run = await s.get(Run, rid)
        if run is None:
            raise HTTPException(404, "run not found")
        await _project_access(request, run.project_id, "viewer")
        rows = (
            (
                await s.execute(
                    select(RunResult).where(RunResult.run_id == rid).order_by(RunResult.id)
                )
            )
            .scalars()
            .all()
        )
        return [_result(x) for x in rows]


@router.post("/runs/{rid}/cancel")
async def cancel_run(rid: int, request: Request) -> dict:
    async with db_session() as s:
        r = await s.get(Run, rid)
        if r is None:
            raise HTTPException(404, "run not found")
        await _project_access(request, r.project_id, "editor")
        if r.status in ("pending", "running"):
            r.status = "cancelled"
        return _run(r)


# strip any stack of re-run prefixes so names don't nest ("re-run of re-run of …")
_RERUN_PREFIX = re.compile(r"^(re-run of ((failures|errors) in )?)+")

# Which of the previous run's cases to take, keyed on their verdict. A case with no result
# row at all counts as an error — no verdict is an infra outcome, not a product one.
_RERUN_SETS = {
    "failing": lambda st: st != "passed",  # judge failures AND infra errors
    "error": lambda st: st == "error",  # infra errors + timeouts only
}
_RERUN_NAMES = {"failing": "failures", "error": "errors"}


@router.post("/runs/{rid}/rerun")
async def rerun(
    rid: int, request: Request, only: str | None = None, failed_only: bool = False
) -> dict:
    """Re-run an existing run's cases. `only` narrows the set:

    - unset: every case, exactly as before.
    - failing: everything that did not pass. After fixing something you want the verdict on
      what was broken, not another hour re-proving what passed (49 cases ≈ 2h, its failures
      ≈ 30min).
    - error: only the infra outcomes — timeouts, dead sessions, crashed browsers. A judge
      'failed' is a finding about the product and re-running it proves nothing; an 'error'
      means the tool never got a verdict, so it is the one worth another attempt.
    """
    if failed_only and only is None:  # accept the older SPA's parameter
        only = "failing"
    if only is not None and only not in _RERUN_SETS:
        raise HTTPException(400, f"unknown re-run set {only!r}")
    async with db_session() as s:
        old = await s.get(Run, rid)
        if old is None:
            raise HTTPException(404, "run not found")
        await _project_access(request, old.project_id, "editor")
        case_ids = list(old.case_ids or [])
        base = _RERUN_PREFIX.sub("", old.name)
        name = f"re-run of {base}"
        if only is not None:
            rows = (
                (await s.execute(select(RunResult).where(RunResult.run_id == rid))).scalars().all()
            )
            verdict = {r.case_id: r.status for r in rows}
            keep = _RERUN_SETS[only]
            case_ids = [c for c in case_ids if keep(verdict.get(c, "error"))]
            if not case_ids:
                raise HTTPException(400, f"this run has no {only} cases to re-run")
            name = f"re-run of {_RERUN_NAMES[only]} in {base}"
        # the project's current 并发数 wins over whatever the original run was created
        # with — otherwise raising it in settings silently does nothing for re-runs, which
        # is exactly when you are trying to make a two-hour run shorter.
        project = await s.get(Project, old.project_id)
        new = Run(
            project_id=old.project_id,
            name=name,
            case_ids=case_ids,
            concurrency=(project.run_concurrency if project else None) or old.concurrency,
            total_count=len(case_ids),
            environment_id=old.environment_id or await _default_env_id(s, old.project_id),
        )
        s.add(new)
        await s.flush()
        new_id = new.id
        payload = _run(new)
    await _launch(new_id)
    return payload


@router.patch("/runs/{rid}")
async def update_run(rid: int, body: RunPatch, request: Request) -> dict:
    """Rename a run."""
    async with db_session() as s:
        r = await s.get(Run, rid)
        if r is None:
            raise HTTPException(404, "run not found")
        await _project_access(request, r.project_id, "editor")
        r.name = body.name
        return _run(r)


@router.delete("/runs/{rid}")
async def delete_run(rid: int, request: Request) -> dict:
    """Delete a run and its results. A running run is cancelled first."""
    async with db_session() as s:
        r = await s.get(Run, rid)
        if r is None:
            raise HTTPException(404, "run not found")
        await _project_access(request, r.project_id, "editor")
        await s.execute(delete(RunResult).where(RunResult.run_id == rid))
        await s.delete(r)
    return {"deleted": rid}


@router.get("/runs/{rid}/export")
async def export_run(rid: int, request: Request) -> Response:
    """Download a run's per-case results as CSV (case metadata joined in)."""
    async with db_session() as s:
        run = await s.get(Run, rid)
        if run is None:
            raise HTTPException(404, "run not found")
        await _project_access(request, run.project_id, "viewer")
        results = (
            (
                await s.execute(
                    select(RunResult).where(RunResult.run_id == rid).order_by(RunResult.id)
                )
            )
            .scalars()
            .all()
        )
        cases = (
            (await s.execute(select(TestCase).where(TestCase.id.in_([x.case_id for x in results]))))
            .scalars()
            .all()
        )
    by_case = {c.id: c for c in cases}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "case_key",
            "name",
            "module",
            "priority",
            "status",
            "attempts",
            "flaky",
            "latency_ms",
            "judge_reason",
        ]
    )
    for x in results:
        c = by_case.get(x.case_id)
        writer.writerow(
            [
                (c.case_key if c else "") or f"#{x.case_id}",
                c.name if c else "",
                (c.module if c else "") or "",
                c.priority if c else "",
                x.status,
                x.attempts,
                "yes" if x.flaky else "",
                x.latency_ms,
                (x.judge_reason or x.error or "").replace("\n", " "),
            ]
        )
    filename = f"run-{rid}-results.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{rid}/stream")
async def stream_run(rid: int, request: Request) -> EventSourceResponse:
    async with db_session() as s:
        r0 = await s.get(Run, rid)
        if r0 is None:
            raise HTTPException(404, "run not found")
        await _project_access(request, r0.project_id, "viewer")

    async def gen() -> Any:
        while True:
            async with db_session() as s:
                r = await s.get(Run, rid)
            if r is None:
                yield {"event": "error", "data": "run not found"}
                return
            import json

            yield {"event": "progress", "data": json.dumps(_run(r))}
            if r.status in ("completed", "failed", "cancelled"):
                return
            await asyncio.sleep(1.0)

    return EventSourceResponse(gen())


# ---- issues (Kanban) ----
# ---- test suites ----
async def _user_label(s, uid: int | None) -> str | None:
    if uid is None:
        return None
    u = await s.get(User, uid)
    return (u.name or u.email) if u else None


async def _suite(s, x: TestSuite) -> dict:
    return {
        "id": x.id,
        "project_id": x.project_id,
        "name": x.name,
        "description": x.description,
        "selection_mode": x.selection_mode,
        "case_ids": x.case_ids or [],
        "tag_filter": x.tag_filter or [],
        "owner_user_id": x.owner_user_id,
        "owner_label": await _user_label(s, x.owner_user_id),
        "runner_user_id": x.runner_user_id,
        "runner_label": await _user_label(s, x.runner_user_id),
        "environment_id": x.environment_id,
        "cadence": x.cadence,
        "due_at": _iso(x.due_at),
        "last_run_id": x.last_run_id,
        "last_status": x.last_status,
        "last_run_at": _iso(x.last_run_at),
        "created_at": _iso(x.created_at),
    }


async def _resolve_suite_case_ids(s, x: TestSuite) -> list[int]:
    """Concrete, still-existing case ids for a suite (tag filter resolved live)."""
    if x.selection_mode == "tags" and x.tag_filter:
        wanted = set(x.tag_filter)
        rows = (
            (
                await s.execute(
                    select(TestCase).where(
                        TestCase.project_id == x.project_id, TestCase.enabled == True
                    )
                )
            )
            .scalars()
            .all()
        )
        return [c.id for c in rows if wanted & set(c.tags or [])]
    ids = x.case_ids or []
    if not ids:
        return []
    keep = set(
        (
            await s.execute(
                select(TestCase.id).where(TestCase.id.in_(ids), TestCase.project_id == x.project_id)
            )
        )
        .scalars()
        .all()
    )
    return [i for i in ids if i in keep]


@router.get("/projects/{pid}/suites")
async def list_suites(pid: int, request: Request) -> list[dict]:
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        rows = (
            (
                await s.execute(
                    select(TestSuite)
                    .where(TestSuite.project_id == pid)
                    .order_by(TestSuite.id.desc())
                )
            )
            .scalars()
            .all()
        )
        return [await _suite(s, x) for x in rows]


@router.post("/projects/{pid}/suites")
async def create_suite(pid: int, body: SuiteIn, request: Request) -> dict:
    await _project_access(request, pid, "editor")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        user = await auth.current_user(request)
        x = TestSuite(
            project_id=pid,
            **body.model_dump(),
            due_at=_next_due(body.cadence),
            created_by=user.email if user else None,
        )
        s.add(x)
        await s.flush()
        if x.runner_user_id is not None:
            await notify.push(
                s,
                user_id=x.runner_user_id,
                type="assigned",
                title=f"你被指派为套件执行人:{x.name}",
                body="请按约定周期运行该测试套件并复核结果。",
                link=f"/projects/{pid}/suites",
                suite_id=x.id,
            )
        return await _suite(s, x)


@router.get("/suites/{sid}")
async def get_suite(sid: int, request: Request) -> dict:
    async with db_session() as s:
        x = await s.get(TestSuite, sid)
        if x is None:
            raise HTTPException(404, "suite not found")
        await _project_access(request, x.project_id, "viewer")
        return await _suite(s, x)


@router.put("/suites/{sid}")
async def update_suite(sid: int, body: SuitePatch, request: Request) -> dict:
    async with db_session() as s:
        x = await s.get(TestSuite, sid)
        if x is None:
            raise HTTPException(404, "suite not found")
        await _project_access(request, x.project_id, "editor")
        prev_runner = x.runner_user_id
        data = body.model_dump(exclude_none=True)
        for k, v in data.items():
            setattr(x, k, v)
        if "cadence" in data:  # recompute next due from the new cadence
            x.due_at = _next_due(x.cadence, x.last_run_at)
        await s.flush()
        if x.runner_user_id is not None and x.runner_user_id != prev_runner:
            await notify.push(
                s,
                user_id=x.runner_user_id,
                type="assigned",
                title=f"你被指派为套件执行人:{x.name}",
                body="请按约定周期运行该测试套件并复核结果。",
                link=f"/projects/{x.project_id}/suites",
                suite_id=x.id,
            )
        return await _suite(s, x)


@router.post("/suites/{sid}/assign")
async def assign_suite(sid: int, body: SuiteAssignIn, request: Request) -> dict:
    async with db_session() as s:
        x = await s.get(TestSuite, sid)
        if x is None:
            raise HTTPException(404, "suite not found")
        await _project_access(request, x.project_id, "editor")
        changed = x.runner_user_id != body.runner_user_id
        x.runner_user_id = body.runner_user_id
        await s.flush()
        if changed and x.runner_user_id is not None:
            await notify.push(
                s,
                user_id=x.runner_user_id,
                type="assigned",
                title=f"你被指派为套件执行人:{x.name}",
                body="请按约定周期运行该测试套件并复核结果。",
                link=f"/projects/{x.project_id}/suites",
                suite_id=x.id,
            )
        return await _suite(s, x)


@router.delete("/suites/{sid}")
async def delete_suite(sid: int, request: Request) -> dict:
    async with db_session() as s:
        x = await s.get(TestSuite, sid)
        if x is None:
            raise HTTPException(404, "suite not found")
        await _project_access(request, x.project_id, "editor")
        await s.delete(x)
        return {"deleted": sid}


@router.post("/suites/{sid}/run")
async def run_suite_now(sid: int, request: Request) -> dict:
    """Any project member may run a suite; the Run records who actually ran it."""
    async with db_session() as s:
        x = await s.get(TestSuite, sid)
        if x is None:
            raise HTTPException(404, "suite not found")
        await _project_access(request, x.project_id, "viewer")
        user = await auth.current_user(request)
        project = await s.get(Project, x.project_id)
        case_ids = await _resolve_suite_case_ids(s, x)
        if not case_ids:
            raise HTTPException(400, "suite has no runnable cases")
        run = Run(
            project_id=x.project_id,
            name=x.name,
            case_ids=case_ids,
            concurrency=(project.run_concurrency if project else None) or 2,
            total_count=len(case_ids),
            suite_id=x.id,
            ran_by_user_id=user.id if user else None,
            trigger="suite",
            environment_id=x.environment_id or await _default_env_id(s, x.project_id),
            created_by=user.email if user else None,
        )
        s.add(run)
        await s.flush()
        run_id = run.id
        payload = _run(run)
    await _launch(run_id)
    return payload


# ---- notifications (per current user) ----
def _notif(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "suite_id": n.suite_id,
        "run_id": n.run_id,
        "issue_id": n.issue_id,
        "read": n.read_at is not None,
        "created_at": _iso(n.created_at),
    }


@router.get("/notifications")
async def list_notifications(request: Request) -> list[dict]:
    user = await auth.current_user(request)
    if user is None:
        return []
    async with db_session() as s:
        rows = (
            (
                await s.execute(
                    select(Notification)
                    .where(Notification.user_id == user.id)
                    .order_by(Notification.read_at.isnot(None), Notification.created_at.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
        return [_notif(n) for n in rows]


@router.get("/notifications/unread-count")
async def unread_count(request: Request) -> dict:
    user = await auth.current_user(request)
    if user is None:
        return {"count": 0}
    async with db_session() as s:
        n = (
            await s.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == user.id, Notification.read_at.is_(None))
            )
        ).scalar_one()
        return {"count": n}


@router.post("/notifications/{nid}/read")
async def read_notification(nid: int, request: Request) -> dict:
    user = await auth.current_user(request)
    async with db_session() as s:
        n = await s.get(Notification, nid)
        if n is None or (user is not None and n.user_id != user.id):
            raise HTTPException(404, "notification not found")
        if n.read_at is None:
            n.read_at = datetime.now(UTC)
        return {"ok": True}


@router.post("/notifications/read-all")
async def read_all_notifications(request: Request) -> dict:
    user = await auth.current_user(request)
    if user is None:
        return {"ok": True}
    async with db_session() as s:
        rows = (
            (
                await s.execute(
                    select(Notification).where(
                        Notification.user_id == user.id, Notification.read_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        now = datetime.now(UTC)
        for n in rows:
            n.read_at = now
        return {"ok": True, "marked": len(rows)}


def _issue(i: Issue) -> dict:
    return {
        "id": i.id,
        "project_id": i.project_id,
        "title": i.title,
        "description": i.description,
        "status": i.status,
        "severity": i.severity,
        "assignee": i.assignee,
        "assignee_user_id": i.assignee_user_id,
        "labels": i.labels or [],
        "case_id": i.case_id,
        "run_id": i.run_id,
        "result_id": i.result_id,
        "gitlab_iid": i.gitlab_iid,
        "gitlab_url": _gitlab_web_url(i.gitlab_project, i.gitlab_iid),
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "updated_at": i.updated_at.isoformat() if i.updated_at else None,
    }


def _comment(c: IssueComment) -> dict:
    return {
        "id": c.id,
        "issue_id": c.issue_id,
        "body": c.body,
        "author": c.author,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/projects/{pid}/issues")
async def list_issues(pid: int, request: Request, status: str | None = None) -> list[dict]:
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        q = select(Issue).where(Issue.project_id == pid).order_by(Issue.id.desc())
        if status:
            q = q.where(Issue.status == status)
        return [_issue(i) for i in (await s.execute(q)).scalars().all()]


@router.post("/projects/{pid}/issues")
async def create_issue(pid: int, body: IssueIn, request: Request) -> dict:
    await _project_access(request, pid, "editor")
    async with db_session() as s:
        await _get_project_or_404(s, pid)
        i = Issue(project_id=pid, **body.model_dump())
        s.add(i)
        await s.flush()
        if i.assignee_user_id is not None:
            await notify.push(
                s,
                user_id=i.assignee_user_id,
                type="issue_assigned",
                title=f"你被指派了问题:{i.title}",
                body=f"严重度 {i.severity}。",
                link=f"/projects/{pid}/issues",
                issue_id=i.id,
            )
        enqueue_push(i.id)  # auto-push every new issue (no-ops if project has no GitLab config)
        issue_id = i.id
        payload = _issue(i)
    await feishu_notify.mirror_issue(issue_id)  # mirror to the project's Bitable (best-effort)
    return payload


@router.get("/issues/{iid}")
async def get_issue(iid: int, request: Request) -> dict:
    async with db_session() as s:
        i = await s.get(Issue, iid)
        if i is None:
            raise HTTPException(404, "issue not found")
        await _project_access(request, i.project_id, "viewer")
        comments = (
            (
                await s.execute(
                    select(IssueComment)
                    .where(IssueComment.issue_id == iid)
                    .order_by(IssueComment.id)
                )
            )
            .scalars()
            .all()
        )
        return {**_issue(i), "comments": [_comment(c) for c in comments]}


@router.put("/issues/{iid}")
async def update_issue(iid: int, body: IssuePatch, request: Request) -> dict:
    async with db_session() as s:
        i = await s.get(Issue, iid)
        if i is None:
            raise HTTPException(404, "issue not found")
        await _project_access(request, i.project_id, "editor")
        prev_assignee = i.assignee_user_id
        prev_status = i.status
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(i, k, v)
        await s.flush()
        status_changed = i.status != prev_status
        if i.assignee_user_id is not None and i.assignee_user_id != prev_assignee:
            await notify.push(
                s,
                user_id=i.assignee_user_id,
                type="issue_assigned",
                title=f"你被指派了问题:{i.title}",
                body=f"严重度 {i.severity},当前状态 {i.status}。",
                link=f"/projects/{i.project_id}/issues",
                issue_id=i.id,
            )
        enqueue_push(i.id)  # mirror status/field edits up to GitLab
        issue_id = i.id
        payload = _issue(i)
    if status_changed:
        await feishu_notify.push_issue_update(issue_id)  # best-effort push to bound chat
        await feishu_notify.sync_issue_to_bitable(issue_id)  # write status back to Bitable
    return payload


@router.delete("/issues/{iid}")
async def delete_issue(iid: int, request: Request) -> dict:
    async with db_session() as s:
        i = await s.get(Issue, iid)
        if i is None:
            raise HTTPException(404, "issue not found")
        await _project_access(request, i.project_id, "editor")
        await s.delete(i)
        return {"deleted": iid}


@router.post("/issues/{iid}/comments")
async def add_comment(iid: int, body: IssueCommentIn, request: Request) -> dict:
    async with db_session() as s:
        i = await s.get(Issue, iid)
        if i is None:
            raise HTTPException(404, "issue not found")
        await _project_access(request, i.project_id, "editor")
        c = IssueComment(issue_id=iid, body=body.body, author=body.author)
        s.add(c)
        await s.flush()
        enqueue_push(iid)  # push mirrors unsynced comments up as GitLab notes
        return _comment(c)


# ---- feishu feedback bot ----
def _feedback(f: FeedbackItem) -> dict:
    return {
        "id": f.id,
        "source": f.source,
        "chat_id": f.chat_id,
        "chat_type": f.chat_type,
        "sender_id": f.sender_id,
        "sender_name": f.sender_name,
        "content": f.content,
        "title": f.title,
        "category": f.category,
        "severity": f.severity,
        "answer": f.answer,
        "answered": f.answered,
        "status": f.status,
        "project_id": f.project_id,
        "issue_id": f.issue_id,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@public.post("/feishu/events")
async def feishu_events(request: Request) -> dict:
    """Feishu event subscription callback (Feishu posts here; no user auth).

    Handles the url_verification handshake and dispatches message events to a
    background worker, returning 200 immediately so Feishu doesn't retry (3s).
    """
    body = await request.json()
    if "encrypt" in body:
        # Leave "Encrypt Key" blank in the Feishu console — decryption unsupported.
        raise HTTPException(400, "encrypted events not supported; clear the Encrypt Key")
    async with db_session() as s:
        token = (await feishu.resolve_config(s))["verification_token"]
    if body.get("type") == "url_verification":
        if token and body.get("token") != token:
            raise HTTPException(403, "bad verification token")
        return {"challenge": body.get("challenge")}
    header = body.get("header") or {}
    if token and header.get("token") != token:
        raise HTTPException(403, "bad verification token")
    if header.get("event_type") == "im.message.receive_v1":
        feishu.schedule(body)
    return {"code": 0}


@router.get("/projects/{pid}/feedback")
async def list_project_feedback(
    pid: int,
    request: Request,
    status: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Feishu-collected feedback for one project, newest first."""
    await _project_access(request, pid, "viewer")
    async with db_session() as s:
        q = (
            select(FeedbackItem)
            .where(FeedbackItem.project_id == pid)
            .order_by(FeedbackItem.id.desc())
        )
        if status:
            q = q.where(FeedbackItem.status == status)
        if category:
            q = q.where(FeedbackItem.category == category)
        q = q.limit(min(max(limit, 1), 200))
        return [_feedback(f) for f in (await s.execute(q)).scalars().all()]


@router.post("/feedback/{fid}/promote")
async def promote_feedback(fid: int, request: Request) -> dict:
    """Convert a feedback item into an Issue on its project's board (idempotent)."""
    async with db_session() as s:
        f = await s.get(FeedbackItem, fid)
        if f is None:
            raise HTTPException(404, "feedback not found")
        if f.project_id is None:
            raise HTTPException(400, "feedback has no project — bind the chat first")
        await _project_access(request, f.project_id, "editor")
        if f.issue_id is not None:
            existing = await s.get(Issue, f.issue_id)
            if existing is not None:
                return _issue(existing)
        i = Issue(
            project_id=f.project_id,
            title=f.title or f.content[:60],
            description=f.content,
            severity=f.severity,
            labels=["feishu"],
            created_by=f.sender_id,
        )
        s.add(i)
        await s.flush()
        f.issue_id = i.id
        issue_id = i.id
        payload = _issue(i)
    enqueue_push(issue_id)
    await feishu_notify.mirror_issue(issue_id)
    return payload


# ---- artifacts ----
@router.get("/results/{rid}/video")
async def result_video(rid: int, request: Request) -> RedirectResponse:
    return await _redirect_artifact(rid, "video_url", request)


@router.get("/results/{rid}/trace")
async def result_trace(rid: int, request: Request) -> RedirectResponse:
    return await _redirect_artifact(rid, "trace_url", request)


async def _redirect_artifact(rid: int, field: str, request: Request) -> RedirectResponse:
    async with db_session() as s:
        x = await s.get(RunResult, rid)
        if x is None:
            raise HTTPException(404, "result not found")
        run = await s.get(Run, x.run_id)
        await _project_access(request, run.project_id, "viewer")
        url = getattr(x, field)
        if not url:
            raise HTTPException(404, f"no {field}")
        return RedirectResponse(url)
