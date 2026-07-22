from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced from environment / .env.

    No user personal data is ever stored here — only infra + toggles.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "change-me-dev-only-not-a-real-secret"
    api_cors_origins: str = "http://localhost:3000"

    # SQLite by default so the system runs with zero infrastructure.
    database_url: str = "sqlite+aiosqlite:///./data/job_os.db"
    redis_url: str = "redis://localhost:6379/0"

    # Object storage (private).
    s3_endpoint_url: str = ""
    s3_bucket: str = "job-os-private"

    # Connector politeness.
    connector_user_agent: str = "PersonalJobApplicationOS/0.1 (+personal-use)"
    connector_default_rate_limit_per_min: int = 30
    connector_http_timeout_seconds: float = 20.0

    # LLM is optional. Empty provider => rule-based only (fully offline).
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_strict_pii_minimization: bool = True

    # Single-principal API token. Empty => protected routes refuse to serve.
    api_token: str = ""

    session_cookie_name: str = "job_os_session"
    session_ttl_minutes: int = 1440

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def async_database_url(self) -> str:
        """Normalize provider-supplied URLs to an async driver.

        Render/Railway expose ``postgres://`` / ``postgresql://``; the async
        engine needs the asyncpg driver. SQLite URLs pass through unchanged.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        return url

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_provider and self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
