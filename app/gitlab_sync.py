"""GitLab <-> TestPilot issue reconciliation.

Field model:
  * TestPilot status (open|in_progress|fixed|verified|closed) is carried on the GitLab
    side as a scoped label `status::<status>`; the GitLab open/closed state is *derived*
    (verified/closed -> closed, everything else -> open).
  * severity -> scoped label `severity::<severity>`; free labels pass through untouched.
  * comments <-> notes, deduped by IssueComment.gitlab_note_id.

Conflict rule: last-writer-wins by updated_at. `last_sync_hash` lets the poller tell
whether the GitLab side actually changed since we last reconciled.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.crypto import decrypt, secret_configured
from app.db import db_session
from app.gitlab_client import GitLabClient
from app.models import Credential, Issue, IssueComment, Project

log = logging.getLogger("testpilot.gitlab")

_CLOSED_STATUSES = {"verified", "closed"}
_STATUSES = ("open", "in_progress", "fixed", "verified", "closed")


# ---- pure mapping helpers (unit-tested) ----
def status_to_labels(status: str, severity: str, extra: list[str]) -> list[str]:
    """The full label set GitLab should carry for this issue (scoped + passthrough)."""
    passthrough = [x for x in extra if not x.startswith(("status::", "severity::"))]
    return [f"status::{status}", f"severity::{severity}", *passthrough]


def state_event_for(status: str) -> str:
    return "close" if status in _CLOSED_STATUSES else "reopen"


def labels_to_status(labels: list[str], gl_state: str) -> str:
    for lb in labels:
        if lb.startswith("status::"):
            s = lb.split("::", 1)[1]
            if s in _STATUSES:
                return s
    # no scoped label -> derive from GitLab open/closed
    return "closed" if gl_state == "closed" else "open"


def labels_to_severity(labels: list[str], default: str) -> str:
    for lb in labels:
        if lb.startswith("severity::"):
            return lb.split("::", 1)[1]
    return default


def passthrough_labels(labels: list[str]) -> list[str]:
    return [x for x in labels if not x.startswith(("status::", "severity::"))]


def sync_hash(title: str, status: str, severity: str, labels: list[str]) -> str:
    blob = json.dumps(
        {"t": title, "s": status, "sev": severity, "l": sorted(passthrough_labels(labels))},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _parse_gl_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ---- token / client wiring ----
async def resolve_token(session, project_id: int) -> str | None:
    """The token to use for a project: its own encrypted token if set, else the
    server-wide GITLAB_TOKEN. Returns None when neither is configured."""
    if secret_configured():
        cred = (
            (
                await session.execute(
                    select(Credential)
                    .where(
                        Credential.project_id == project_id,
                        Credential.type == "gitlab_token",
                        Credential.is_active == True,  # noqa: E712
                    )
                    .order_by(Credential.id.desc())
                )
            )
            .scalars()
            .first()
        )
        if cred is not None:
            return decrypt(cred.secret)
    # global token: admin-set app_setting first, then the env fallback
    from app.settings_store import GITLAB_TOKEN_KEY, get_setting

    return (await get_setting(session, GITLAB_TOKEN_KEY)) or get_settings().gitlab_token or None


async def _client_for(session, project: Project) -> GitLabClient | None:
    if not project.gitlab_project:
        return None
    token = await resolve_token(session, project.id)
    if not token:
        return None
    return GitLabClient(token, project.gitlab_project)


def _backlink(issue: Issue) -> str:
    if issue.run_id and issue.result_id:
        return f"\n\n---\n_TestPilot issue #{issue.id} · run {issue.run_id} / result {issue.result_id}_"
    return f"\n\n---\n_TestPilot issue #{issue.id}_"


# ---- push: TestPilot -> GitLab ----
async def push_issue(issue_id: int) -> None:
    """Create or update the mapped GitLab issue, then mirror unsynced comments up."""
    async with db_session() as s:
        issue = await s.get(Issue, issue_id)
        if issue is None:
            return
        project = await s.get(Project, issue.project_id)
        if project is None:
            return
        client = await _client_for(s, project)
        if client is None:
            log.info("push skipped: project %s has no GitLab config", issue.project_id)
            return

        labels = status_to_labels(issue.status, issue.severity, issue.labels or [])
        h = sync_hash(issue.title, issue.status, issue.severity, issue.labels or [])

        if issue.gitlab_iid is None:
            created = await client.create_issue(
                title=issue.title,
                description=(issue.description or "") + _backlink(issue),
                labels=",".join(labels),
            )
            issue.gitlab_iid = created["iid"]
            issue.gitlab_project = project.gitlab_project
            # a freshly-created issue is open; close it if the status says so
            if issue.status in _CLOSED_STATUSES:
                await client.edit_issue(issue.gitlab_iid, state_event="close")
        else:
            await client.edit_issue(
                issue.gitlab_iid,
                title=issue.title,
                labels=",".join(labels),
                state_event=state_event_for(issue.status),
            )
        issue.last_sync_hash = h
        issue.last_synced_at = datetime.now(UTC)

        # mirror comments that haven't been pushed yet
        unsynced = (
            (
                await s.execute(
                    select(IssueComment).where(
                        IssueComment.issue_id == issue.id, IssueComment.gitlab_note_id.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        for c in unsynced:
            note = await client.create_note(issue.gitlab_iid, c.body)
            c.gitlab_note_id = note["id"]


# ---- pull: GitLab -> TestPilot (poller) ----
async def poll_project(project_id: int) -> int:
    """Reconcile recently-changed GitLab issues into local ones. Returns #reconciled."""
    reconciled = 0
    changed_status_ids: list[int] = []
    async with db_session() as s:
        project = await s.get(Project, project_id)
        if project is None:
            return 0
        client = await _client_for(s, project)
        if client is None:
            return 0

        local = (
            (
                await s.execute(
                    select(Issue).where(
                        Issue.project_id == project_id, Issue.gitlab_iid.is_not(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        by_iid = {i.gitlab_iid: i for i in local}
        if not by_iid:
            return 0

        gl_issues = await client.list_issues()
        for gl in gl_issues:
            issue = by_iid.get(gl["iid"])
            if issue is None:
                continue
            gl_updated = _parse_gl_ts(gl.get("updated_at"))
            gl_status = labels_to_status(gl.get("labels", []), gl.get("state", "opened"))
            gl_severity = labels_to_severity(gl.get("labels", []), issue.severity)
            gl_hash = sync_hash(gl.get("title", ""), gl_status, gl_severity, gl.get("labels", []))

            if gl_hash == issue.last_sync_hash:
                await _pull_notes(s, client, issue)
                continue

            # last-writer-wins
            local_newer = (
                gl_updated is not None
                and issue.updated_at is not None
                and (issue.updated_at > gl_updated)
            )
            if local_newer:
                # local wins -> push handled elsewhere; skip applying GitLab's stale copy
                continue

            if issue.status != gl_status:
                changed_status_ids.append(issue.id)
            issue.title = gl.get("title", issue.title)
            issue.status = gl_status
            issue.severity = gl_severity
            issue.labels = passthrough_labels(gl.get("labels", []))
            issue.last_sync_hash = gl_hash
            issue.last_synced_at = gl_updated
            reconciled += 1
            await _pull_notes(s, client, issue)

    # GitLab → us applied; propagate the status change to the Bitable (best-effort).
    if changed_status_ids:
        from app import feishu_notify

        for iid in changed_status_ids:
            await feishu_notify.sync_issue_to_bitable(iid)
    return reconciled


async def _pull_notes(session, client: GitLabClient, issue: Issue) -> None:
    """Add GitLab notes we haven't seen as local comments (skips system notes)."""
    seen = {
        c.gitlab_note_id
        for c in (
            await session.execute(select(IssueComment).where(IssueComment.issue_id == issue.id))
        )
        .scalars()
        .all()
        if c.gitlab_note_id is not None
    }
    for note in await client.list_notes(issue.gitlab_iid):
        if note.get("system") or note["id"] in seen:
            continue
        session.add(
            IssueComment(
                issue_id=issue.id,
                body=note.get("body", ""),
                author=(note.get("author") or {}).get("username"),
                gitlab_note_id=note["id"],
            )
        )
