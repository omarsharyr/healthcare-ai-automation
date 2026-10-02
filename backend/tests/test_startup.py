import logging
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from app.db import migrate, startup


def test_database_wait_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock(spec=Engine)
    connection_context = MagicMock()
    engine.connect.side_effect = [OperationalError("SELECT 1", {}, RuntimeError("unavailable")), connection_context]
    sleep = Mock()
    monkeypatch.setattr(startup.time, "sleep", sleep)
    startup.wait_for_database(engine, attempts=3, interval_seconds=2)
    assert engine.connect.call_count == 2
    connection_context.__enter__.return_value.execute.assert_called_once()
    sleep.assert_called_once_with(2)


def test_database_wait_is_bounded_and_safe(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    engine = MagicMock(spec=Engine)
    engine.connect.side_effect = OperationalError("SELECT 1", {}, RuntimeError("synthetic_password"))
    sleep = Mock()
    monkeypatch.setattr(startup.time, "sleep", sleep)
    with pytest.raises(RuntimeError, match="Database unavailable"):
        startup.wait_for_database(engine, attempts=3, interval_seconds=2)
    assert engine.connect.call_count == 3
    assert sleep.call_count == 2
    assert "synthetic_password" not in caplog.text


def test_failed_migration_command_exits_nonzero_without_credentials(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(migrate, "configure_logging", lambda *args: None)
    monkeypatch.setattr(migrate, "get_database_settings", Mock(side_effect=RuntimeError("synthetic_password")))
    with caplog.at_level(logging.ERROR):
        assert migrate.main() == 1
    assert "migrations_failed" in caplog.text
    assert "synthetic_password" not in caplog.text
