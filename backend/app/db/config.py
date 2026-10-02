from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # A full URL remains available for host-based Phase 2 development.
    database_url: SecretStr | None = None
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_user: str = "healthcare"
    postgres_password: SecretStr | None = None
    postgres_db: str = "healthcare"
    db_connect_timeout: int = Field(default=3, ge=1, le=30)
    db_pool_timeout: int = Field(default=3, ge=1, le=30)
    db_statement_timeout_ms: int = Field(default=3000, ge=100, le=60000)
    db_startup_attempts: int = Field(default=15, ge=1, le=60)
    db_retry_interval_seconds: float = Field(default=2, ge=0, le=30)
    db_migration_lock_timeout_seconds: int = Field(default=30, ge=1, le=300)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value():
            return None
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from None
        if url.drivername != "postgresql+psycopg" or not url.database:
            raise ValueError("DATABASE_URL must use postgresql+psycopg and name a database")
        return value

    @model_validator(mode="after")
    def require_credentials(self) -> "DatabaseSettings":
        if self.database_url is None and (
            self.postgres_password is None or not self.postgres_password.get_secret_value()
        ):
            raise ValueError("Set POSTGRES_PASSWORD or DATABASE_URL")
        return self

    def sqlalchemy_url(self) -> URL:
        if self.database_url is not None:
            return make_url(self.database_url.get_secret_value())
        assert self.postgres_password is not None
        return URL.create(
            "postgresql+psycopg", username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host, port=self.postgres_port, database=self.postgres_db,
        )


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
