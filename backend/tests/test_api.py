from uuid import UUID

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_request(client: TestClient, synthetic_request: dict[str, str]) -> None:
    response = client.post("/api/v1/requests", json=synthetic_request)
    assert response.status_code == 202
    body = response.json()
    assert UUID(body["request_id"]).version == 4
    assert body["status"] == "accepted"
    assert body["persisted"] is False
    assert "not been stored or queued" in body["message"]
    assert "patient_reference" not in body
    assert "request_text" not in body
    second = client.post("/api/v1/requests", json=synthetic_request)
    assert second.json()["request_id"] != body["request_id"]


def test_invalid_short_request(client: TestClient, synthetic_request: dict[str, str]) -> None:
    synthetic_request["request_text"] = "   short   "
    response = client.post("/api/v1/requests", json=synthetic_request)
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "request_text"]
    assert error["type"] == "string_too_short"
    assert "input" not in error


def test_invalid_priority(client: TestClient, synthetic_request: dict[str, str]) -> None:
    synthetic_request["priority"] = "invalid"
    response = client.post("/api/v1/requests", json=synthetic_request)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "priority"]
