from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=Path(__file__).resolve().parents[4] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = "AI Healthcare Workflow Automation Platform"
    environment: str = "development"
    version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
