"""Verify the published local workflow using synthetic data and real database reads.

Run from the repository root: .venv/Scripts/python.exe n8n/verify_intake.py
Creates one synthetic request and leaves its audit record in place.
"""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request as HttpRequest, urlopen
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import func, select

from app.db.session import get_session_factory
from app.models import AuditEvent, Request


class VerificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    n8n_port: int = 5678


def post(url: str, payload: object) -> tuple[int, dict]:
    request = HttpRequest(url, data=json.dumps(payload).encode(), method="POST",
                          headers={"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=40)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def main() -> None:
    url = f"http://127.0.0.1:{VerificationSettings().n8n_port}/webhook/healthcare-request-intake"
    sample = json.loads((ROOT / "sample-data" / "n8n-request.json").read_text())
    status, body = post(url, sample)
    assert status == 201, f"Expected webhook HTTP 201, got {status}"
    assert body["persisted"] is True and body["source"] == "n8n"
    request_uuid = UUID(body["request_uuid"])
    with get_session_factory()() as session:
        request = session.scalar(select(Request).where(Request.request_uuid == request_uuid))
        assert request is not None and request.source.value == "n8n"
        assert request.request_text == sample["request_text"]
        assert request.patient_reference == sample["patient_reference"]
        assert request.priority.value == "high"
        events = session.scalars(select(AuditEvent).where(AuditEvent.request_id == request.id)).all()
        assert len(events) == 1 and events[0].event_type == "REQUEST_RECEIVED"
        assert events[0].event_metadata == {"source": "n8n", "priority": "high"}
        before = session.scalar(select(func.count()).select_from(Request))
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
    for payload, expected in [
        ({**sample, "priority": "invalid"}, 422),
        ({**sample, "request_text": "short"}, 422),
        ({**sample, "unexpected": "synthetic"}, 422),
        ([sample], 400),
    ]:
        status, error = post(url, payload)
        assert status == expected, f"Expected HTTP {expected}, got {status}"
        assert sample["patient_reference"] not in json.dumps(error)
    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(Request)) == before
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
    print(f"PASS: webhook -> FastAPI -> request + REQUEST_RECEIVED audit; UUID={request_uuid}")
    print("PASS: invalid priority/text/extra fields return 422; non-object envelope returns 400; no extra rows.")


if __name__ == "__main__":
    main()
