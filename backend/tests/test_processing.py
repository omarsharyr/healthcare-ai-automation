import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AuditEvent, HumanReview, Request
from app.services.ai_provider import FakeAIProvider, get_ai_provider
from app.services.phi_redaction import PHIRedactionService

pytestmark = pytest.mark.integration


def classification(category: str = "CLAIM_STATUS", confidence: float = 0.95,
                   action: str = "AUTO_PROCESS") -> str:
    return json.dumps({"category": category, "confidence": confidence, "recommended_action": action,
                       "reason": "Synthetic classification reason."})


def create(client: TestClient, payload: dict[str, str]) -> str:
    response = client.post("/api/v1/requests", json=payload)
    assert response.status_code == 201
    return response.json()["request_uuid"]


def audit_types(sessions: sessionmaker[Session]) -> list[str]:
    with sessions() as session:
        return list(session.scalars(select(AuditEvent.event_type).order_by(AuditEvent.id)))


def test_processing_redacts_before_provider_and_audits_safely(
    db_client: TestClient, db_sessions: sessionmaker[Session], synthetic_request: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    class InspectingProvider(FakeAIProvider):
        calls = 0

        def classify(self, redacted_text: str) -> str:
            self.calls += 1
            for value in ("PAT-10042", "CLM-9999", "1995-10-02", "fake@example.test", "202-555-0199"):
                assert value not in redacted_text
            assert all(marker in redacted_text for marker in ("[PATIENT_ID]", "[CLAIM_ID]", "[DOB]", "[EMAIL]", "[PHONE]"))
            return classification()

    provider = InspectingProvider()
    db_client.app.dependency_overrides[get_ai_provider] = lambda: provider
    synthetic_request["request_text"] = "Patient PAT-10042 DOB 1995-10-02 claim CLM-9999 status; fake@example.test 202-555-0199"
    uuid = create(db_client, synthetic_request)
    response = db_client.post(f"/api/v1/requests/{uuid}/process")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["system_decision"] == "AUTO_PROCESS"
    assert body["confidence"] == 0.95
    assert body["review_id"] is None
    assert db_client.post(f"/api/v1/requests/{uuid}/process").json() == body
    assert provider.calls == 1
    assert audit_types(db_sessions) == ["REQUEST_RECEIVED", "PHI_REDACTION_COMPLETED", "AI_CLASSIFICATION_STARTED",
        "AI_CLASSIFICATION_COMPLETED", "WORKFLOW_DECISION_MADE", "WORKFLOW_COMPLETED"]
    with db_sessions() as session:
        request = session.scalar(select(Request))
        assert request is not None and request.request_text == synthetic_request["request_text"]
        assert session.scalar(select(func.count()).select_from(HumanReview)) == 0
        metadata = json.dumps([row.event_metadata for row in session.scalars(select(AuditEvent))])
    for value in ("PAT-10042", "CLM-9999", "1995-10-02", "fake@example.test", "202-555-0199"):
        assert value not in metadata + caplog.text + response.text


@pytest.mark.parametrize("provider", [FakeAIProvider(fail=True), FakeAIProvider("not JSON")])
def test_ai_failure_and_invalid_output_create_human_review(
    db_client: TestClient, db_sessions: sessionmaker[Session], synthetic_request: dict[str, str], provider: FakeAIProvider,
) -> None:
    db_client.app.dependency_overrides[get_ai_provider] = lambda: provider
    uuid = create(db_client, synthetic_request)
    response = db_client.post(f"/api/v1/requests/{uuid}/process")
    assert response.status_code == 200
    body = response.json()
    assert body["system_decision"] == "HUMAN_REVIEW"
    assert body["category"] is None and body["confidence"] is None and body["ai_recommendation"] is None
    assert body["review_id"] is not None
    assert "AI_CLASSIFICATION_FAILED" in audit_types(db_sessions)
    assert "HUMAN_REVIEW_REQUESTED" in audit_types(db_sessions)
    assert "WORKFLOW_COMPLETED" not in audit_types(db_sessions)


@pytest.mark.parametrize("action,status,decision", [("approve", "APPROVED", "AUTO_PROCESS"), ("reject", "REJECTED", "REJECT")])
def test_human_review_and_duplicate_protection(
    db_client: TestClient, db_sessions: sessionmaker[Session], synthetic_request: dict[str, str],
    action: str, status: str, decision: str,
) -> None:
    uuid = create(db_client, synthetic_request)
    body = db_client.post(f"/api/v1/requests/{uuid}/process").json()
    assert body["system_decision"] == "HUMAN_REVIEW"
    review_id = body["review_id"]
    queue = db_client.get("/api/v1/reviews/pending").json()
    assert len(queue) == 1 and queue[0]["id"] == review_id
    assert "request_text" not in queue[0]
    notes = "Synthetic reviewer note PAT-10042"
    response = db_client.post(f"/api/v1/reviews/{review_id}/{action}", json={"reviewer_notes": notes})
    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()["reviewer_decision"] == decision
    assert response.json()["reviewed_at"] is not None
    assert response.json()["reviewer_notes"] == notes
    assert db_client.get("/api/v1/reviews/pending").json() == []
    for duplicate_action in ("approve", "reject"):
        assert db_client.post(f"/api/v1/reviews/{review_id}/{duplicate_action}").status_code == 409
    assert db_client.get(f"/api/v1/requests/{uuid}").json()["system_decision"] == decision
    assert db_client.post(f"/api/v1/requests/{uuid}/process").json()["system_decision"] == decision
    with db_sessions() as session:
        events = session.scalars(select(AuditEvent)).all()
        assert sum(row.event_type == "HUMAN_REVIEW_COMPLETED" for row in events) == 1
        assert sum(row.event_type == "WORKFLOW_COMPLETED" for row in events) == 1
        assert notes not in json.dumps([row.event_metadata for row in events])
        assert session.scalar(select(func.count()).select_from(HumanReview)) == 1


def test_reject_decision_completes_without_review(db_client: TestClient, synthetic_request: dict[str, str]) -> None:
    db_client.app.dependency_overrides[get_ai_provider] = lambda: FakeAIProvider(classification("DOCUMENT_PROCESSING", 0.95, "REJECT"))
    uuid = create(db_client, synthetic_request)
    body = db_client.post(f"/api/v1/requests/{uuid}/process").json()
    assert body["system_decision"] == "REJECT"
    assert body["review_id"] is None


def test_unknown_requests_and_reviews(db_client: TestClient) -> None:
    assert db_client.post(f"/api/v1/requests/{uuid4()}/process").status_code == 404
    assert db_client.post("/api/v1/reviews/999999/approve").status_code == 404
    assert db_client.post("/api/v1/reviews/999999/reject").status_code == 404


def test_unexpected_processing_failure_is_audited(
    db_client: TestClient, db_sessions: sessionmaker[Session], synthetic_request: dict[str, str],
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(*args: object) -> None:
        raise RuntimeError("PAT-10042 synthetic_password")
    monkeypatch.setattr(PHIRedactionService, "redact", fail)
    uuid = create(db_client, synthetic_request)
    response = db_client.post(f"/api/v1/requests/{uuid}/process")
    assert response.status_code == 500
    assert db_client.get(f"/api/v1/requests/{uuid}").json()["status"] == "failed"
    assert db_client.post(f"/api/v1/requests/{uuid}/process").status_code == 409
    assert audit_types(db_sessions) == ["REQUEST_RECEIVED", "WORKFLOW_FAILED"]
    assert "synthetic_password" not in caplog.text + response.text


def test_concurrent_processing_calls_provider_once(
    db_client: TestClient, db_sessions: sessionmaker[Session], synthetic_request: dict[str, str],
) -> None:
    entered, release = Event(), Event()
    class BlockingProvider(FakeAIProvider):
        calls = 0

        def classify(self, redacted_text: str) -> str:
            self.calls += 1
            entered.set()
            assert release.wait(5)
            return classification("OTHER", 0.99)

    provider = BlockingProvider()
    db_client.app.dependency_overrides[get_ai_provider] = lambda: provider
    uuid = create(db_client, synthetic_request)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(db_client.post, f"/api/v1/requests/{uuid}/process")
        try:
            assert entered.wait(5)
            assert db_client.post(f"/api/v1/requests/{uuid}/process").status_code == 409
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
    assert provider.calls == 1
    with db_sessions() as session:
        assert session.scalar(select(func.count()).select_from(HumanReview)) == 1


def test_concurrent_review_resolutions_have_one_winner(
    db_client: TestClient, db_sessions: sessionmaker[Session], synthetic_request: dict[str, str],
) -> None:
    uuid = create(db_client, synthetic_request)
    review_id = db_client.post(f"/api/v1/requests/{uuid}/process").json()["review_id"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda action: db_client.post(f"/api/v1/reviews/{review_id}/{action}"), ("approve", "reject")))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert audit_types(db_sessions).count("HUMAN_REVIEW_COMPLETED") == 1
