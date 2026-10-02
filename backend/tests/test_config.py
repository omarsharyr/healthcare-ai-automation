from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.config import DatabaseSettings


def test_environment_files_resolve_to_repository_root(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repository / "backend")
    for settings_class in (Settings, DatabaseSettings):
        env_file = settings_class.model_config["env_file"]
        assert env_file == repository / ".env"
        assert env_file.is_absolute()


def test_database_url_is_secret_and_environment_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql+psycopg://fake:synthetic_password@localhost/healthcare_test"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = DatabaseSettings(_env_file=None)
    assert settings.database_url.get_secret_value() == url
    assert "synthetic_password" not in repr(settings)


def test_database_configuration_rejects_non_postgres_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///synthetic_password.db")
    with pytest.raises(ValidationError) as error:
        DatabaseSettings(_env_file=None)
    assert "synthetic_password" not in str(error.value)


def test_database_parts_handle_password_special_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("POSTGRES_PASSWORD", "synthetic@:/?#%password")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    settings = DatabaseSettings(_env_file=None)
    url = settings.sqlalchemy_url()
    assert url.host == "postgres"
    assert url.password == "synthetic@:/?#%password"
    assert "synthetic@" not in repr(settings)


def test_database_password_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    with pytest.raises(ValidationError):
        DatabaseSettings(_env_file=None)
