import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.ai_config import AISettings
from app.core.enums import WorkflowDecision
from app.services.ai_provider import AIProviderError, FakeAIProvider, OpenAIProvider
from app.services.phi_redaction import PHIRedactionService
from app.services.request_classifier import RequestClassifier
from app.services.workflow_decision import WorkflowDecisionService


def output(category: str = "CLAIM_STATUS", confidence: float = 0.95, action: str = "AUTO_PROCESS") -> str:
    return json.dumps({"category": category, "confidence": confidence, "recommended_action": action,
                       "reason": "Synthetic classification."})


def test_redaction_example() -> None:
    result = PHIRedactionService().redact("Patient PAT-12345 DOB 1995-10-02 says claim CLM-9999 was rejected.")
    assert result.text == "Patient [PATIENT_ID] DOB [DOB] says claim [CLAIM_ID] was rejected."
    assert result.counts == {"PATIENT_ID": 1, "CLAIM_ID": 1, "DOB": 1}
    assert "PAT-12345" not in repr(result)


@pytest.mark.parametrize("raw, marker", [
    ("MRN: 123456", "[PATIENT_ID]"), ("CLM-9999", "[CLAIM_ID]"),
    ("claim ID: ABC123", "[CLAIM_ID]"), ("fake.person@example.test", "[EMAIL]"),
    ("+1 (202) 555-0199", "[PHONE]"), ("202-555-0199", "[PHONE]"),
    ("+8801712345678", "[PHONE]"), ("DOB: 10/02/1995", "[DOB]"),
    ("date of birth October 2, 1995", "[DOB]"), ("DOB 2 October 1995", "[DOB]"),
])
def test_common_sensitive_patterns(raw: str, marker: str) -> None:
    redacted = PHIRedactionService().redact(raw)
    assert marker in redacted.text
    assert raw not in redacted.text


def test_redaction_preserves_plain_text_and_is_repeatable() -> None:
    service = PHIRedactionService()
    original = "Additional information is required for the claim."
    assert service.redact(original).text == original
    first = service.redact("Contact PAT-12345 at synthetic@example.test")
    assert service.redact(first.text).text == first.text


def test_successful_classification() -> None:
    result = RequestClassifier(FakeAIProvider(output())).classify("Redacted synthetic request")
    assert result.failure is None
    assert result.output is not None and result.output.confidence == 0.95


@pytest.mark.parametrize("raw", [
    "not json", "{}", "[]",
    output(confidence=1.5), output(confidence=-1), output(confidence=float("nan")),
    output(category="INVENTED"), output(action="DELETE_DATABASE"),
    output().replace('0.95', '"0.95"'), output().replace('0.95', 'true'),
    output()[:-1] + ', "extra": "untrusted"}',
])
def test_malformed_ai_outputs_are_not_trusted(raw: str) -> None:
    result = RequestClassifier(FakeAIProvider(raw)).classify("Synthetic request")
    assert result.output is None
    assert result.failure == "invalid_ai_output"
    assert WorkflowDecisionService().decide(result).decision == WorkflowDecision.HUMAN_REVIEW


def test_provider_failure_falls_back_to_review() -> None:
    result = RequestClassifier(FakeAIProvider(fail=True)).classify("Synthetic request")
    assert result.failure == "provider_failure"
    assert WorkflowDecisionService().decide(result).decision == WorkflowDecision.HUMAN_REVIEW


@pytest.mark.parametrize("category,confidence,recommendation,expected", [
    ("CLAIM_STATUS", 0.8499, "AUTO_PROCESS", "HUMAN_REVIEW"),
    ("CLAIM_STATUS", 0.85, "AUTO_PROCESS", "AUTO_PROCESS"),
    ("OTHER", 1.0, "AUTO_PROCESS", "HUMAN_REVIEW"),
    ("DOCUMENT_PROCESSING", 0.95, "REJECT", "REJECT"),
    ("DOCUMENT_PROCESSING", 0.95, "AUTO_PROCESS", "AUTO_PROCESS"),
    ("CLAIM_STATUS", 0.95, "REJECT", "HUMAN_REVIEW"),
    ("BILLING_QUESTION", 0.95, "AUTO_PROCESS", "HUMAN_REVIEW"),
    ("MISSING_INFORMATION", 0.95, "REJECT", "HUMAN_REVIEW"),
    ("CLAIM_STATUS", 0.95, "HUMAN_REVIEW", "HUMAN_REVIEW"),
])
def test_deterministic_decision_rules(category: str, confidence: float, recommendation: str, expected: str) -> None:
    result = RequestClassifier(FakeAIProvider(output(category, confidence, recommendation))).classify("Synthetic")
    assert WorkflowDecisionService().decide(result).decision.value == expected


def test_real_provider_contract_with_mock_http() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url == "https://api.openai.com/v1/responses"
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        assert body["input"] == [{"role": "user", "content": "Patient [PATIENT_ID] requests claim status."}]
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": output()}]},
        ]})
    settings = AISettings(_env_file=None, ai_provider="openai", openai_api_key=SecretStr("synthetic-key"))
    provider = OpenAIProvider(settings, transport=httpx.MockTransport(respond))
    assert RequestClassifier(provider).classify("Patient [PATIENT_ID] requests claim status.").output is not None


@pytest.mark.parametrize("failure", ["http", "timeout", "refusal", "incomplete"])
def test_real_provider_failures_are_safe(failure: str, caplog: pytest.LogCaptureFixture) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic-key PAT-12345", request=request)
        if failure == "http":
            return httpx.Response(401, json={"error": "synthetic-key PAT-12345"})
        return httpx.Response(200, json={"status": "incomplete" if failure == "incomplete" else "completed",
            "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "PAT-12345"}]}]})
    provider = OpenAIProvider(AISettings(_env_file=None, openai_api_key=SecretStr("synthetic-key")),
                              transport=httpx.MockTransport(respond))
    with pytest.raises(AIProviderError) as error:
        provider.classify("[PATIENT_ID]")
    assert "synthetic-key" not in str(error.value) + caplog.text
    assert "PAT-12345" not in str(error.value) + caplog.text
