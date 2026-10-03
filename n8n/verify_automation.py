"""Verify the local published Phase 5 workflow; leaves synthetic demo records.

Requires AI_PROVIDER=fake in the running backend. No paid provider calls.
"""
import json
import subprocess
from uuid import UUID

from verify_intake import ROOT, VerificationSettings, post
from pydantic_settings import SettingsConfigDict
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models import AuditEvent, HumanReview, Request


class Settings(VerificationSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    api_port: int = 8000


def main() -> None:
    # Check the running container, not merely the host .env, before submitting.
    subprocess.run([
        "docker", "compose", "exec", "-T", "backend", "python", "-c",
        "from app.core.ai_config import get_ai_settings; assert get_ai_settings().ai_provider == 'fake', 'Set AI_PROVIDER=fake and recreate backend first'",
    ], cwd=ROOT, check=True, capture_output=True)
    settings = Settings()
    webhook = f"http://127.0.0.1:{settings.n8n_port}/webhook/healthcare-request-automation"
    api = f"http://127.0.0.1:{settings.api_port}/api/v1"
    cases = [
        ("Please check claim status for CLM-9999.", "AUTO_PROCESS", None),
        ("Additional information is required for this claim.", "HUMAN_REVIEW", "approve"),
        ("Missing information is required for this claim.", "HUMAN_REVIEW", "reject"),
        ("An unreadable document was submitted for processing.", "REJECT", None),
    ]
    for text, expected, action in cases:
        sample = {"patient_reference": "PAT-12345", "request_text":
                  f"Patient PAT-12345 DOB 1995-10-02. {text}", "source": "n8n", "priority": "high"}
        status, body = post(webhook, sample)
        assert status == 200, f"Expected webhook HTTP 200, got {status}"
        assert body["system_decision"] == expected and body["persisted"] is True
        request_uuid = UUID(body["request_uuid"])
        with get_session_factory()() as session:
            request = session.scalar(select(Request).where(Request.request_uuid == request_uuid))
            assert request is not None and request.system_decision.value == expected
            events = session.scalars(select(AuditEvent).where(AuditEvent.request_id == request.id).order_by(AuditEvent.id)).all()
            types = [event.event_type for event in events]
            assert types == ["REQUEST_RECEIVED", "PHI_REDACTION_COMPLETED", "AI_CLASSIFICATION_STARTED",
                             "AI_CLASSIFICATION_COMPLETED", "WORKFLOW_DECISION_MADE",
                             "HUMAN_REVIEW_REQUESTED" if action else "WORKFLOW_COMPLETED"]
            assert all("PAT-12345" not in json.dumps(event.event_metadata) for event in events)
            review = session.scalar(select(HumanReview).where(HumanReview.request_id == request.id))
            assert (review is not None) == (action is not None)
            if review:
                assert review.id == body["review_id"] and review.status.value == "PENDING"
        repeat_status, repeat = post(f"{api}/requests/{request_uuid}/process", {})
        assert repeat_status == 200 and repeat["system_decision"] == expected
        if action:
            url = f"{api}/reviews/{body['review_id']}/{action}"
            resolved_status, resolved = post(url, {"reviewer_notes": "Synthetic verification only."})
            assert resolved_status == 200
            assert resolved["status"] == ("APPROVED" if action == "approve" else "REJECTED")
            assert post(url, {})[0] == 409
            with get_session_factory()() as session:
                request = session.scalar(select(Request).where(Request.request_uuid == request_uuid))
                types = session.scalars(select(AuditEvent.event_type).where(AuditEvent.request_id == request.id)).all()
                assert types.count("HUMAN_REVIEW_COMPLETED") == 1
                assert types.count("WORKFLOW_COMPLETED") == 1
                assert request.system_decision.value == ("AUTO_PROCESS" if action == "approve" else "REJECT")
        print(f"PASS: {expected}{' -> ' + action if action else ''}; persisted request/audits; UUID={request_uuid}")
    assert post(webhook, {**sample, "priority": "invalid"})[0] == 422
    print("PASS: invalid input rejected; all three workflow branches and both review actions verified.")


if __name__ == "__main__":
    main()
