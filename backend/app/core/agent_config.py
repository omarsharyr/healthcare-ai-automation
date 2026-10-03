from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_", env_file=Path(__file__).resolve().parents[3] / ".env", extra="ignore")
    max_tool_calls: int = Field(default=5, ge=1, le=10)
    timeout_seconds: float = Field(default=25, ge=0.1, le=40)
    allow_global_count: bool = True


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
