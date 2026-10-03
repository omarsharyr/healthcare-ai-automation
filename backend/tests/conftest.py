from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.session import get_session
from app.main import create_app
from app.services.ai_provider import FakeAIProvider, get_ai_provider
from app.agents.provider import FakeAgentPlanner, get_agent_planner

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestDatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore", hide_input_in_errors=True)
    test_database_url: SecretStr | None = None
    test_postgres_host: str = "127.0.0.1"
    test_postgres_port: int = 5433
    postgres_user: str = "healthcare"
    postgres_password: SecretStr | None = None


def migration_config() -> Config:
    return Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    settings = TestDatabaseSettings()
    configured_url = settings.test_database_url
    if configured_url is not None and configured_url.get_secret_value():
        url = make_url(configured_url.get_secret_value())
    else:
        if settings.postgres_password is None or not settings.postgres_password.get_secret_value():
            pytest.fail("Set POSTGRES_PASSWORD or TEST_DATABASE_URL and start the postgres-test service")
        url = URL.create(
            "postgresql+psycopg", username=settings.postgres_user,
            password=settings.postgres_password.get_secret_value(),
            host=settings.test_postgres_host, port=settings.test_postgres_port, database="healthcare_test",
        )
    if url.drivername != "postgresql+psycopg" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must use postgresql+psycopg and a database ending in _test")
    # Every test owns a new schema. Never migrate, truncate, or drop application tables.
    schema = f"test_{uuid4().hex}"
    admin_engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
    engine = create_engine(
        url, hide_parameters=True,
        connect_args={"connect_timeout": 5, "options": f"-csearch_path={schema}"},
    )
    created = False
    try:
        with admin_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        created = True
        with engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        if created:
            with admin_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        admin_engine.dispose()


@pytest.fixture
def db_sessions(db_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture
def db_client(db_sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    application = create_app()

    def override_session() -> Iterator[Session]:
        with db_sessions() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_ai_provider] = lambda: FakeAIProvider()
    application.dependency_overrides[get_agent_planner] = lambda: FakeAgentPlanner()
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def synthetic_request() -> dict[str, str]:
    return {
        "patient_reference": "PAT-10042",
        "request_text": "The claim was submitted but additional information is required.",
        "source": "api",
        "priority": "normal",
    }
