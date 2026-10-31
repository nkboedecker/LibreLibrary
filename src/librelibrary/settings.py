"""Deployment settings, read from LIBRELIBRARY_* environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything a deployment can configure."""

    model_config = SettingsConfigDict(env_prefix="LIBRELIBRARY_")

    database_url: str = "sqlite:///librelibrary.db"
    migrations_dir: Path = Path("migrations")
    run_migrations_on_startup: bool = True
    local_auth_enabled: bool = True
    login_rate_limit_per_ip: str = "20/minute"
    login_rate_limit_per_username: str = "10/minute"
    login_token_lifetime_days: int = 30
    trusted_proxies: list[str] = []
