"""Per-project Feishu Bitable (多维表格) mirror of feedback records.

Each project binds its own base (app_token + table_id, parsed from the pasted
URL). When a feedback lands we create a row there and remember its record_id;
when the linked Issue changes status we write it back. All best-effort — a
Bitable hiccup never blocks the chat flow.

Fields are matched by NAME and filtered to those the table actually has, so
projects can use slightly different table templates. "缺陷来源" carries the
reporter's name (matching how the team fills it by hand), falling back to the
source category when the name can't be resolved.
"""

from __future__ import annotations

import logging
import re

import httpx

log = logging.getLogger("testpilot.feishu.bitable")

_BASE_URL_RE = re.compile(r"/base/([A-Za-z0-9]+)")
_TABLE_RE = re.compile(r"[?&]table=(tbl[A-Za-z0-9]+)")

# our value -> Bitable single-select option
_SEVERITY = {"critical": "致命", "high": "严重", "medium": "一般", "low": "轻微"}
_CATEGORY = {"bug": "Bug", "feature": "功能优化"}
# our Issue status -> (缺陷状态, 是否解决)
_ISSUE_STATUS = {
    "open": ("待分配", False),
    "in_progress": ("处理中", False),
    "fixed": ("待验证", False),
    "verified": ("已关闭", True),
    "closed": ("已关闭", True),
}
_REPORTER_FIELD = "报告人"

# name-set cache per (app_token, table_id); refreshed on process restart
_FIELDS_CACHE: dict[tuple[str, str], set[str]] = {}


def parse_bitable_url(url: str) -> tuple[str | None, str | None]:
    """Extract (app_token, table_id) from a Feishu base URL; ('', '') clears."""
    if not url or not url.strip():
        return None, None
    app = _BASE_URL_RE.search(url)
    tbl = _TABLE_RE.search(url)
    return (app.group(1) if app else None), (tbl.group(1) if tbl else None)


async def _field_names(client, app: str, table: str, *, refresh: bool = False) -> set[str]:
    key = (app, table)
    if not refresh and key in _FIELDS_CACHE:
        return _FIELDS_CACHE[key]
    token = await client._tenant_token()
    url = f"{client._base}/open-apis/bitable/v1/apps/{app}/tables/{table}/fields"
    async with httpx.AsyncClient(timeout=15) as h:
        data = (await h.get(url, headers={"Authorization": f"Bearer {token}"})).json()
    if data.get("code") != 0:
        log.warning(
            "bitable list fields failed app=%s table=%s resp=%s", app, table, data.get("msg")
        )
        names: set[str] = set()
    else:
        names = {f["field_name"] for f in data["data"]["items"]}
    _FIELDS_CACHE[key] = names
    return names


def issue_source(issue) -> str:
    if issue.run_id:
        return "测试运行"
    if "feishu" in (issue.labels or []):
        return "飞书群反馈"
    return "网页录入"


_SCREENSHOT_FIELD = "问题截图"


async def upload_screenshot(client, app_token: str, data: bytes, filename: str) -> str | None:
    """Upload image bytes as a Bitable attachment; returns the file_token or None."""
    token = await client._tenant_token()
    url = f"{client._base}/open-apis/drive/v1/medias/upload_all"
    async with httpx.AsyncClient(timeout=30) as h:
        resp = (
            await h.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "file_name": filename,
                    "parent_type": "bitable_image",
                    "parent_node": app_token,
                    "size": str(len(data)),
                },
                files={"file": (filename, data)},
            )
        ).json()
    if resp.get("code") != 0:
        log.warning("bitable upload screenshot failed: %s", resp.get("msg"))
        return None
    return (resp.get("data") or {}).get("file_token")


def _issue_fields(
    issue,
    project_name: str,
    reporter_open_id: str | None = None,
    reporter_name: str | None = None,
) -> dict:
    status_cn, solved = _ISSUE_STATUS.get(issue.status, ("待分配", False))
    source = issue_source(issue)
    # 问题备注 carries only machine metadata; the user's own words lead 缺陷描述
    # (with the model summary appended) — reporter feedback stays authoritative.
    # The category lives here since 缺陷来源 itself holds the reporter's name.
    note = f"项目：{project_name} · 来源：{source} · Issue #{issue.id}"
    if issue.gitlab_iid:
        note += f" · GitLab #{issue.gitlab_iid}"
    if issue.run_id:
        note += f" · run #{issue.run_id}"
    desc = issue.title or ""
    original = (issue.description or "").strip()
    if original and original != desc.strip():
        desc = f"{original[:800]}\n\n摘要：{issue.title}" if desc else original[:800]
    fields: dict = {
        "缺陷描述": desc,
        "缺陷来源": reporter_name or source,
        "缺陷状态": status_cn,
        "是否解决": solved,
        "问题备注": note,
    }
    labels = issue.labels or []
    fields["缺陷类型"] = "功能优化" if ("feature" in labels or "功能优化" in labels) else "Bug"
    if issue.severity in _SEVERITY:
        fields["严重级别"] = _SEVERITY[issue.severity]
    if issue.created_at is not None:
        fields["问题日期"] = int(issue.created_at.timestamp() * 1000)
    if reporter_open_id:
        # Only written when the table already has this person field; never created.
        fields[_REPORTER_FIELD] = [{"id": reporter_open_id}]
    return fields


async def create_issue_record(
    client,
    app: str,
    table: str,
    issue,
    project_name: str,
    reporter_open_id: str | None,
    reporter_name: str | None = None,
    screenshot_tokens: list[str] | None = None,
) -> str | None:
    """Create a Bitable defect row for an Issue; returns its record_id or None."""
    names = await _field_names(client, app, table)
    if not names:
        return None
    fields = {
        k: v
        for k, v in _issue_fields(issue, project_name, reporter_open_id, reporter_name).items()
        if k in names
    }
    if screenshot_tokens and _SCREENSHOT_FIELD in names:
        fields[_SCREENSHOT_FIELD] = [{"file_token": t} for t in screenshot_tokens]
    token = await client._tenant_token()
    url = f"{client._base}/open-apis/bitable/v1/apps/{app}/tables/{table}/records"
    async with httpx.AsyncClient(timeout=15) as h:
        data = (
            await h.post(url, headers={"Authorization": f"Bearer {token}"}, json={"fields": fields})
        ).json()
    if data.get("code") != 0:
        log.warning("bitable create record failed: %s", data.get("msg"))
        return None
    return data.get("data", {}).get("record", {}).get("record_id")


async def update_status(client, app: str, table: str, record_id: str, issue_status: str) -> None:
    """Write an Issue's status back to the mirrored Bitable row (best-effort)."""
    mapped = _ISSUE_STATUS.get(issue_status)
    if mapped is None:
        return
    status, solved = mapped
    names = await _field_names(client, app, table)
    fields: dict = {}
    if "缺陷状态" in names:
        fields["缺陷状态"] = status
    if "是否解决" in names:
        fields["是否解决"] = solved
    if not fields:
        return
    token = await client._tenant_token()
    url = f"{client._base}/open-apis/bitable/v1/apps/{app}/tables/{table}/records/{record_id}"
    async with httpx.AsyncClient(timeout=15) as h:
        data = (
            await h.put(url, headers={"Authorization": f"Bearer {token}"}, json={"fields": fields})
        ).json()
    if data.get("code") != 0:
        log.warning("bitable update status failed record=%s: %s", record_id, data.get("msg"))
