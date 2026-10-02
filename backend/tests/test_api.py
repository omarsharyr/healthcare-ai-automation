from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AuditEvent, Request

pytestmark = pytest.mark.integration


def test_valid_request(
    db_client: TestClient, db_sessions: sessionmaker[Session], synthetic_request: dict[str, str],
) -> None:
    response = db_client.post("/api/v1/requests", json=synthetic_request)
    assert response.status_code == 201
    body = response.json()
    request_uuid = UUID(body["request_uuid"])
    assert request_uuid.version == 4
    assert body["status"] == "received"
    assert body["persisted"] is True
    assert body["category"] is None
    assert datetime.fromisoformat(body["created_at"]).utcoffset() is not None
    assert body["created_at"] == body["updated_at"]
    assert "patient_reference" not in body
    assert "request_text" not in body
    assert response.headers["location"] == f"/api/v1/requests/{request_uuid}"
    # A separate session must see committed rows, not just objects in an identity map.
    with db_sessions() as session:
        request = session.scalar(select(Request).where(Request.request_uuid == request_uuid))
        assert request is not None
        assert request.patient_reference == synthetic_request["patient_reference"]
        assert request.request_text == synthetic_request["request_text"]
        events = session.scalars(select(AuditEvent).where(AuditEvent.request_id == request.id)).all()
        assert len(events) == 1
        assert events[0].event_type == "REQUEST_RECEIVED"
        assert events[0].actor == "api"
        assert events[0].event_metadata == {"source": "api", "priority": "normal"}
        assert events[0].created_at.utcoffset() is not None
    second = db_client.post("/api/v1/requests", json=synthetic_request)
    assert second.status_code == 201
    assert second.json()["request_uuid"] != body["request_uuid"]


def test_invalid_short_request(db_client: TestClient, synthetic_request: dict[str, str]) -> None:
    synthetic_request["request_text"] = "   short   "
    response = db_client.post("/api/v1/requests", json=synthetic_request)
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "request_text"]
    assert error["type"] == "string_too_short"
    assert "input" not in error


def test_invalid_priority(
    db_client: TestClient, db_sessions: sessionmaker[Session], synthetic_request: dict[str, str],
) -> None:
    synthetic_request["priority"] = "invalid"
    response = db_client.post("/api/v1/requests", json=synthetic_request)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "priority"]
    with db_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Request)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_get_persisted_request(db_client: TestClient, synthetic_request: dict[str, str]) -> None:
    created = db_client.post("/api/v1/requests", json=synthetic_request).json()
    response = db_client.get(f"/api/v1/requests/{created['request_uuid']}")
    assert response.status_code == 200
    body = response.json()
    assert body["request_uuid"] == created["request_uuid"]
    assert body["status"] == "received"
    assert body["category"] is None
    for field, value in synthetic_request.items():
        assert body[field] == value
    assert "id" not in body


def test_get_unknown_request(db_client: TestClient) -> None:
    response = db_client.get(f"/api/v1/requests/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Request not found"}


def test_get_invalid_uuid(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/requests/not-a-uuid")
    assert response.status_code == 422
    assert "input" not in response.json()["detail"][0]
