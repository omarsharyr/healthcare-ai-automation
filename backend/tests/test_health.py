from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from unittest.mock import Mock

from app.db.session import get_session


def test_health(client: TestClient) -> None:
    # Liveness stays independent of PostgreSQL availability/configuration.
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
def test_ready_with_migrated_postgres(db_client: TestClient) -> None:
    response = db_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_readiness_failure_does_not_affect_liveness(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    session = Mock(spec=Session)
    session.execute.side_effect = OperationalError(
        "SELECT 1", {}, RuntimeError("synthetic_database_password PAT-10042"),
    )
    client.app.dependency_overrides[get_session] = lambda: session
    response = client.get("/health")
    assert response.status_code == 200
    session.execute.assert_not_called()
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
    assert "synthetic_database_password" not in caplog.text + response.text
    assert "PAT-10042" not in caplog.text + response.text


@pytest.mark.integration
def test_ready_requires_migrated_tables(db_client: TestClient, db_engine: Engine) -> None:
    # This engine points only at this test's disposable schema.
    with db_engine.begin() as connection:
        connection.execute(text("DROP TABLE audit_events"))
    response = db_client.get("/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
