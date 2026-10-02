from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def synthetic_request() -> dict[str, str]:
    return {
        "patient_reference": "PAT-10042",
        "request_text": "The claim was submitted but additional information is required.",
        "source": "api",
        "priority": "normal",
    }
