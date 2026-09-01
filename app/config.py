"""Settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./testpilot.db"

    gateway_base_url: str = "https://api.openai.com/v1"
    gateway_api_key: str = ""
    gateway_model: str = "gpt-4o"  # shared default; the judge always uses this
    agent_model: str = ""  # browser-use agent model; empty falls back to gateway_model
    gateway_verify_ssl: bool = True
    gateway_max_tokens: int = 16000  # completion cap for the browser agent's structured output
    report_language: str = "Chinese (简体中文)"  # language for agent reasoning + judge reason

    # Fernet key encrypting stored test credentials at rest (empty => credential API disabled)
    secret_key: str = Field(default="", validation_alias="TESTPILOT_SECRET_KEY")

    # Empty S3_ENDPOINT => store artifacts on local disk under ./artifacts
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "testpilot"
    s3_region: str = "us-east-1"

    default_concurrency: int = 2  # per-run worker count (in-process fallback only)
    # Global ceiling on concurrent browsers across ALL runs/users (each ~0.5 GB RAM).
    # Celery path: set the worker's --concurrency to this (each case == one browser).
    # In-process fallback: an asyncio.Semaphore(this) shared by all runs.
    max_global_concurrency: int = 16
    case_max_steps: int = 30
    case_timeout_s: int = (
        60  # hard wall-clock cap per case (login + task); per-project override wins
    )
    case_retries: int = (
        0  # no auto-retry — a stuck case fails fast instead of burning 2x the timeout
    )
    # How long the app under test keeps a session alive. A captured login is re-used until
    # this runs out, then re-captured once (single-flight) for everyone. Most systems sit
    # around 30 minutes, so stay just under it.
    session_ttl_min: int = 25

    artifact_dir: str = "./artifacts"

    # Built frontend (web/dist) served by the API as an SPA. Empty => API only
    # (dev uses the Vite server). The Docker image sets this to /app/web_dist.
    web_dist: str = ""

    # GitLab two-way issue sync (Celery worker + beat). Empty redis_url => sync disabled.
    redis_url: str = ""  # e.g. redis://localhost:6379/0 — Celery broker/result backend
    gitlab_base_url: str = "https://gitlab.com/api/v4"
    gitlab_verify_ssl: bool = True
    gitlab_poll_interval_s: int = 60
    # Server-wide GitLab token (api scope). When set, projects need only pick a
    # GitLab project — no per-project token. A per-project token still overrides it.
    gitlab_token: str = ""

    # --- auth / users ---
    # auth_enabled stays False until the login UI ships, so the app keeps working
    # no-login during the rollout; flip it on to require login + enforce RBAC.
    auth_enabled: bool = False
    # Per-project RBAC by default: a user sees only projects an admin assigned them to
    # (ProjectMember owner/editor/viewer); admins see all. Set True for a shared workspace
    # where any logged-in user has full access to every project (login gate only).
    shared_workspace: bool = False
    jwt_secret: str = ""  # HS256 signing key; required once auth_enabled
    jwt_ttl_hours: int = 24 * 7
    admin_email: str = ""  # seeds the first admin on startup (with admin_password)
    admin_password: str = ""
    # Canonical public URL (domain). Drives BOTH email links (invites/notifications)
    # and the address shown in the UI. Set via PUBLIC_BASE_URL, e.g. http://testpilot.example.com
    public_base_url: str = ""

    # --- Feishu (Lark) feedback bot ---
    # Self-built app credentials (飞书开放平台 自建应用). Empty => webhook disabled.
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    # Event subscription Verification Token. When set, incoming events must match.
    feishu_verification_token: str = ""
    # Open API base. Cloud 飞书: https://open.feishu.cn ; Lark 国际版: https://open.larksuite.com
    feishu_api_base: str = "https://open.feishu.cn"
    # Also answer questions detected from context (not just @-mentions / p2p).
    feishu_auto_answer_detected: bool = True
    # Ambient monitoring cost gate: non-@ messages need a problem keyword to be
    # processed. Set False to LLM-classify EVERY non-@ message (never drop, higher cost).
    feishu_ambient_require_keyword: bool = True

    # --- system SMTP (invite emails / notifications) ---
    email_from: str = "noreply@example.com"
    email_host: str = "smtp.example.com"
    email_port: int = 25
    email_host_user: str = ""
    email_host_password: str = ""
    email_use_ssl: bool = False
    email_use_tls: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
