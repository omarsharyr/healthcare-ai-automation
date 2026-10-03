from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        extra="ignore", hide_input_in_errors=True,
    )
    ai_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    ai_timeout_seconds: float = Field(default=20, ge=1, le=30)


@lru_cache
def get_ai_settings() -> AISettings:
    return AISettings()
