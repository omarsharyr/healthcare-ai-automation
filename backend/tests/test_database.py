from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Mapper, Session, sessionmaker

from app.models import AuditEvent, Request
from app.db.migrate import MIGRATION_LOCK_ID, upgrade_database
from app.schemas.requests import RequestCreate
from app.services.requests import create_request
from conftest import migration_config

pytestmark = pytest.mark.integration


def test_audit_failure_rolls_back_request(
    db_client: TestClient, db_sessions: sessionmaker[Session],
    synthetic_request: dict[str, str], caplog: pytest.LogCaptureFixture,
) -> None:
    def invalidate_actor(mapper: Mapper[AuditEvent], connection: Connection, target: AuditEvent) -> None:
        # Force a real NOT NULL violation during audit INSERT.
        target.actor = None  # type: ignore[assignment]

    event.listen(AuditEvent, "before_insert", invalidate_actor)
    try:
        response = db_client.post("/api/v1/requests", json=synthetic_request)
    finally:
        event.remove(AuditEvent, "before_insert", invalidate_actor)
    assert response.status_code == 503
    assert response.json() == {"detail": "Database operation failed"}
    with db_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Request)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    for value in (synthetic_request["request_text"], synthetic_request["patient_reference"]):
        assert value not in response.text
        assert value not in caplog.text


def test_commit_failure_does_not_return_success(
    db_client: TestClient, db_sessions: sessionmaker[Session], synthetic_request: dict[str, str],
) -> None:
    def fail_commit(session: Session) -> None:
        raise OperationalError("COMMIT", {}, RuntimeError("Synthetic commit failure"))

    event.listen(db_sessions, "before_commit", fail_commit)
    try:
        response = db_client.post("/api/v1/requests", json=synthetic_request)
    finally:
        event.remove(db_sessions, "before_commit", fail_commit)
    assert response.status_code == 503
    with db_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Request)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_duplicate_uuid_is_rejected(db_sessions: sessionmaker[Session], synthetic_request: dict[str, str]) -> None:
    with db_sessions() as session:
        created = create_request(session, RequestCreate(**synthetic_request))
    with db_sessions() as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(Request(request_uuid=created.request_uuid, **synthetic_request))


def test_audit_requires_existing_request(db_sessions: sessionmaker[Session]) -> None:
    with db_sessions() as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(AuditEvent(request_id=999999, event_type="REQUEST_RECEIVED", actor="api"))


def test_database_rejects_invalid_priority(db_engine: Engine) -> None:
    # Raw SQL bypasses Pydantic/ORM to verify the migration's actual DB constraint.
    with pytest.raises(IntegrityError), db_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO requests (request_uuid, patient_reference, request_text, source, priority) "
            "VALUES (:uuid, 'PAT-10042', 'Synthetic claim question', 'api', 'urgent')"
        ), {"uuid": uuid4()})


def test_updated_at_changes_on_orm_update(
    db_sessions: sessionmaker[Session], synthetic_request: dict[str, str],
) -> None:
    with db_sessions() as session:
        created = create_request(session, RequestCreate(**synthetic_request))
    with db_sessions() as session, session.begin():
        request = session.scalar(select(Request).where(Request.request_uuid == created.request_uuid))
        assert request is not None
        request.request_text = "Updated synthetic request text."
    with db_sessions() as session:
        request = session.scalar(select(Request).where(Request.request_uuid == created.request_uuid))
        assert request is not None
        assert request.created_at == created.created_at
        assert request.updated_at > created.updated_at


def test_migration_round_trip_and_model_alignment(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        config = migration_config()
        config.attributes["connection"] = connection
        command.check(config)
        command.downgrade(config, "base")
        assert "requests" not in inspect(connection).get_table_names()
        assert "audit_events" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert {"requests", "audit_events"}.issubset(inspect(connection).get_table_names())
        command.check(config)


def test_migration_runner_is_repeatable(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        config = migration_config()
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    # Exercise first-time schema creation as well as repeated upgrades.
    upgrade_database(db_engine)
    upgrade_database(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"


def test_migration_runner_respects_concurrent_lock(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_ID})
        with pytest.raises(OperationalError):
            upgrade_database(db_engine, lock_timeout_seconds=1)
    # A failed lock acquisition must not damage the schema or keep the lock.
    upgrade_database(db_engine)
