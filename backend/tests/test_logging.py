import json
import logging
import sys

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter


def test_formatter_emits_json_and_omits_extra_data_and_tracebacks() -> None:
    try:
        raise RuntimeError("synthetic_database_password")
    except RuntimeError:
        record = logging.LogRecord("app", logging.ERROR, __file__, 1, "database_operation_failed", (), sys.exc_info())
    record.patient_reference = "PAT-10042"
    record.request_text = "Synthetic private request."
    record.status_code = 503
    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)
    assert payload["event"] == "database_operation_failed"
    assert payload["status_code"] == 503
    assert payload["level"] == "ERROR"
    for sensitive in ("synthetic_database_password", "PAT-10042", "Synthetic private request."):
        assert sensitive not in formatted


def test_request_logs_exclude_payload_and_raw_urls(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app")
    client.get("/api/v1/requests/not-a-uuid?patient_reference=PAT-10042")
    client.get("/PAT-10042/Synthetic-secret")
    client.post("/api/v1/requests", json={"patient_reference": "PAT-10042", "request_text": "short"})
    records = [record for record in caplog.records if record.name == "app.main" and record.msg == "http_request_completed"]
    assert [record.route for record in records] == ["/api/v1/requests/{request_uuid}", "unmatched", "/api/v1/requests"]
    for record in records:
        payload = JsonFormatter().format(record)
        assert "PAT-10042" not in payload
        assert "short" not in payload
        assert "Synthetic-secret" not in payload
        assert record.duration_ms >= 0


def test_unexpected_error_response_and_logs_are_generic(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    @client.app.get("/synthetic-error")
    def fail() -> None:
        raise RuntimeError("synthetic_database_password PAT-10042")

    response = client.get("/synthetic-error")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "request_failed" in caplog.text
    assert "synthetic_database_password" not in caplog.text + response.text
    assert "PAT-10042" not in caplog.text + response.text
