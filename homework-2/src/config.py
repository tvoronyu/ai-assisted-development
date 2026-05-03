from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default="postgresql+asyncpg://tickets:tickets@localhost:5432/tickets")

    # 512 MiB cap on bulk-import upload size. Balances support for large CSV/XML
    # batches against per-request memory pressure on the worker. When raising
    # this, also raise worker memory limits and request timeouts to avoid OOM.
    max_upload_size_bytes: int = Field(default=512 * 1024 * 1024)

    log_level: str = Field(default="INFO")
    app_env: str = Field(default="development")


@lru_cache
def get_settings() -> Settings:
    return Settings()
