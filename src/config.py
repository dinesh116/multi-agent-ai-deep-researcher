"""Settings from environment variables (.env). Secrets are read here and never stored or displayed in full."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_research"

load_dotenv(PROJECT_ROOT / ".env")
# Default to suppressing graph-state and model payloads before LangSmith initializes.
os.environ.setdefault("LANGSMITH_HIDE_INPUTS", "true")
os.environ.setdefault("LANGSMITH_HIDE_OUTPUTS", "true")

APP_NAME = "Deep Researcher AI"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None
    openrouter_model: str
    openrouter_base_url: str
    tavily_api_key: str | None
    contact_email: str | None
    db_path: Path
    http_timeout: float
    llm_timeout: float
    max_upload_mb: int
    turso_database_url: str | None = None  # libsql://<db>-<org>.<region>.turso.io (not secret on its own)
    turso_auth_token: str | None = None  # secret
    input_usd_per_million: float = 0.0
    output_usd_per_million: float = 0.0
    app_env: str = "production"  # local mode must be explicitly enabled; deployments require authentication
    admin_emails: tuple[str, ...] = ()  # signed-in users who may change app-wide settings

    @property
    def uses_turso(self) -> bool:
        return bool(self.turso_database_url and self.turso_auth_token)

    @property
    def llm_configured(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def web_search_configured(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def mask_secret(secret: str | None) -> str:
    """Show only that a key exists and its last 4 characters."""
    if not secret:
        return "not configured"
    return f"configured (…{secret[-4:]})" if len(secret) > 8 else "configured"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    app_env = (_env("APP_ENV", "production") or "production").lower()
    if app_env not in {"local", "production"}:
        raise ValueError("APP_ENV must be local or production.")
    db = Path(_env("APP_DB_PATH", "data/research.db"))
    return Settings(
        openrouter_api_key=_env("OPENROUTER_API_KEY"),
        openrouter_model=_env("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        openrouter_base_url=_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        tavily_api_key=_env("TAVILY_API_KEY"),
        contact_email=_env("CONTACT_EMAIL"),
        db_path=db if db.is_absolute() else PROJECT_ROOT / db,
        http_timeout=float(_env("HTTP_TIMEOUT_SECONDS", "20")),
        llm_timeout=float(_env("LLM_TIMEOUT_SECONDS", "60")),
        max_upload_mb=int(_env("MAX_UPLOAD_MB", "15")),
        turso_database_url=_env("TURSO_DATABASE_URL"),
        turso_auth_token=_env("TURSO_AUTH_TOKEN"),
        input_usd_per_million=max(0.0, float(_env("LLM_INPUT_USD_PER_MILLION", "0"))),
        output_usd_per_million=max(0.0, float(_env("LLM_OUTPUT_USD_PER_MILLION", "0"))),
        app_env=app_env,
        admin_emails=tuple(e.strip().lower() for e in (_env("ADMIN_EMAILS", "") or "").split(",") if e.strip()),
    )
