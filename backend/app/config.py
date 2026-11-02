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
    ai_mode: str = "fake"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    mail_mode: str = "console"
    public_base_url: str = "http://localhost:8000"
    sourcing_manager_email: str = "sourcing@example.test"
    master_data_email: str = "master-data@example.test"
    inbox_mode: str = "manual"
    gmail_label: str = "vendor-requests"
    tz: str = "Asia/Dubai"


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""

    return Settings()
