from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from app.schemas.ai import AIClassification
from app.services.ai_provider import AIProvider


@dataclass(frozen=True)
class ClassificationResult:
    output: AIClassification | None = None
    failure: Literal["provider_failure", "invalid_ai_output"] | None = None


class RequestClassifier:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    def classify(self, redacted_text: str) -> ClassificationResult:
        try:
            raw = self.provider.classify(redacted_text)
        except Exception:
            return ClassificationResult(failure="provider_failure")
        try:
            if not isinstance(raw, str) or len(raw) > 16000:
                return ClassificationResult(failure="invalid_ai_output")
            return ClassificationResult(output=AIClassification.model_validate_json(raw))
        except (ValidationError, ValueError):
            return ClassificationResult(failure="invalid_ai_output")
