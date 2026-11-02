"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Secrets come from environment variables only."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    database_url: str
    admin_token: str
    token_secret: str
    tz: str = "Asia/Dubai"


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""

    return Settings()
