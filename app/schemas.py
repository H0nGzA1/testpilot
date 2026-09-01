"""Request bodies validated at the API boundary (Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_url: str | None = None
    login_state: str | None = None  # storage_state JSON string


class ProjectPatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    case_timeout_s: int | None = Field(default=None, ge=15, le=600)
    case_max_steps: int | None = Field(default=None, ge=3, le=100)
    run_concurrency: int | None = Field(default=None, ge=1, le=16)
    feishu_chat_id: str | None = None  # "" unbinds; bot routes runs/pushes to this chat
    feishu_bitable_url: str | None = None  # paste the base URL; "" clears the binding


Priority = Literal["P0", "P1", "P2", "P3"]
CaseType = Literal["functional", "smoke", "regression", "acceptance", "negative"]
CaseStatus = Literal["draft", "active", "deprecated"]


class TestStep(BaseModel):
    action: str = ""
    expected: str = ""


class TestCaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    prompt: str = Field(min_length=1)  # the NL task the agent executes
    expected: str = ""
    case_key: str | None = None  # auto-assigned (TC-001) when omitted
    module: str | None = None
    priority: Priority = "P2"
    type: CaseType = "functional"
    status: CaseStatus = "active"
    owner: str | None = None
    role: str | None = None  # multi-account: which role/account this case runs as
    references: str = ""
    preconditions: str = ""
    steps: list[TestStep] = Field(default_factory=list)  # documentation, not executed
    test_data: str = ""
    start_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class TestCasePatch(BaseModel):
    name: str | None = None
    prompt: str | None = None
    expected: str | None = None
    case_key: str | None = None
    module: str | None = None
    priority: Priority | None = None
    type: CaseType | None = None
    status: CaseStatus | None = None
    owner: str | None = None
    role: str | None = None
    references: str | None = None
    preconditions: str | None = None
    steps: list[TestStep] | None = None
    test_data: str | None = None
    start_url: str | None = None
    tags: list[str] | None = None
    enabled: bool | None = None


class EnvironmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str | None = None
    is_default: bool = False


class EnvironmentPatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    is_default: bool | None = None


class CredentialIn(BaseModel):
    type: Literal["storage_state", "password"]
    role: str | None = None  # multi-account: the role this account plays
    environment_id: int | None = None  # environment this account belongs to (null = any)
    label: str = ""
    username: str | None = None  # required for type=password
    secret: str = Field(min_length=1)  # storage_state JSON, or the password (encrypted server-side)


class CredentialCaptureIn(BaseModel):
    """Server logs into the project's base_url with this test account and captures the
    resulting session (no CLI). Password is used to log in and stored encrypted for refresh."""

    label: str = ""
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class IssueIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    description: str = ""
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    assignee: str | None = None
    assignee_user_id: int | None = None
    labels: list[str] = Field(default_factory=list)
    case_id: int | None = None
    run_id: int | None = None
    result_id: int | None = None


class IssuePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    status: Literal["open", "in_progress", "fixed", "verified", "closed"] | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    assignee: str | None = None
    assignee_user_id: int | None = None
    labels: list[str] | None = None


Cadence = Literal["none", "daily", "weekly", "biweekly", "monthly"]


class SuiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    selection_mode: Literal["cases", "tags"] = "cases"
    case_ids: list[int] = Field(default_factory=list)
    tag_filter: list[str] = Field(default_factory=list)
    owner_user_id: int | None = None
    runner_user_id: int | None = None
    cadence: Cadence = "none"
    environment_id: int | None = None


class SuitePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    selection_mode: Literal["cases", "tags"] | None = None
    case_ids: list[int] | None = None
    tag_filter: list[str] | None = None
    owner_user_id: int | None = None
    runner_user_id: int | None = None
    cadence: Cadence | None = None
    environment_id: int | None = None


class SuiteAssignIn(BaseModel):
    runner_user_id: int | None = None


class RolesIn(BaseModel):
    roles: list[str] = Field(default_factory=list)


class IssueCommentIn(BaseModel):
    body: str = Field(min_length=1)
    author: str | None = None


class GitLabConfigIn(BaseModel):
    gitlab_project: str = Field(default="", max_length=400)  # "" unlinks
    token: str | None = None  # write-only; omit to keep the current token


class LoginIn(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


ProjectRole = Literal["owner", "editor", "viewer"]


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    is_admin: bool = False
    project_id: int | None = None
    project_role: ProjectRole = "editor"


class InviteAcceptIn(BaseModel):
    name: str = Field(default="", max_length=120)
    password: str = Field(min_length=6)


class MemberIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: ProjectRole = "editor"


class MemberPatch(BaseModel):
    role: ProjectRole


class UserPatch(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


class GitlabTokenIn(BaseModel):
    token: str = ""  # "" clears the global token


class FeishuSettingsIn(BaseModel):
    # Non-secret fields: None => leave unchanged; "" => clear.
    app_id: str | None = None
    api_base: str | None = None
    auto_answer_detected: bool | None = None
    # Secrets: blank/None => keep the stored value; non-empty => replace.
    app_secret: str | None = None
    verification_token: str | None = None


class RunIn(BaseModel):
    name: str = "run"
    case_ids: list[int] | None = None  # None => all enabled cases in the project
    tags: list[str] | None = None  # optional filter when case_ids omitted
    concurrency: int = Field(default=2, ge=1, le=16)
    environment_id: int | None = None  # target environment (null => project default base_url)


class RunPatch(BaseModel):
    name: str = Field(min_length=1, max_length=300)
