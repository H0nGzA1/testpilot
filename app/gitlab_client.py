"""Thin async GitLab REST v4 client — only the issue/notes surface the sync needs.

One instance per (base_url, token, project). `project` is a numeric id or a
"group/path" string; it's URL-encoded into the /projects/:id path either way.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings


class GitLabError(RuntimeError):
    pass


class GitLabClient:
    def __init__(
        self,
        token: str,
        project: str,
        *,
        base_url: str | None = None,
        verify_ssl: bool | None = None,
    ) -> None:
        s = get_settings()
        self._base = (base_url or s.gitlab_base_url).rstrip("/")
        self._verify = s.gitlab_verify_ssl if verify_ssl is None else verify_ssl
        self._headers = {"PRIVATE-TOKEN": token}
        self._proj = quote(str(project), safe="")

    def _url(self, path: str) -> str:
        return f"{self._base}/projects/{self._proj}{path}"

    async def _request(self, method: str, path: str, **kw: Any) -> Any:
        async with httpx.AsyncClient(verify=self._verify, timeout=30.0) as c:
            r = await c.request(method, self._url(path), headers=self._headers, **kw)
        if r.status_code >= 400:
            raise GitLabError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    # ---- discovery (base-level, not scoped to self._proj) ----
    async def list_accessible_projects(self, search: str | None = None) -> list[dict]:
        """Projects the token's user is a member of (for the settings dropdown)."""
        params: dict[str, Any] = {
            "membership": True,
            "simple": True,
            "per_page": 100,
            "order_by": "last_activity_at",
        }
        if search:
            params["search"] = search
        async with httpx.AsyncClient(verify=self._verify, timeout=30.0) as c:
            r = await c.get(f"{self._base}/projects", headers=self._headers, params=params)
        if r.status_code >= 400:
            raise GitLabError(f"GET /projects -> {r.status_code}: {r.text[:300]}")
        return r.json() or []

    # ---- issues ----
    async def create_issue(self, **fields: Any) -> dict:
        return await self._request("POST", "/issues", json=fields)

    async def edit_issue(self, iid: int, **fields: Any) -> dict:
        return await self._request("PUT", f"/issues/{iid}", json=fields)

    async def get_issue(self, iid: int) -> dict:
        return await self._request("GET", f"/issues/{iid}")

    async def list_issues(self, *, updated_after: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"per_page": 100, "order_by": "updated_at", "sort": "desc"}
        if updated_after:
            params["updated_after"] = updated_after
        return await self._request("GET", "/issues", params=params) or []

    # ---- notes (comments) ----
    async def list_notes(self, iid: int) -> list[dict]:
        return await self._request("GET", f"/issues/{iid}/notes", params={"per_page": 100}) or []

    async def create_note(self, iid: int, body: str) -> dict:
        return await self._request("POST", f"/issues/{iid}/notes", json={"body": body})
