from dataclasses import dataclass

from app.core.enums import RequestCategory, WorkflowDecision
from app.services.request_classifier import ClassificationResult


@dataclass(frozen=True)
class DecisionResult:
    decision: WorkflowDecision
    reason: str


class WorkflowDecisionService:
    def decide(self, result: ClassificationResult) -> DecisionResult:
        output = result.output
        if output is None:
            reason = "Invalid AI output; human review required." if result.failure == "invalid_ai_output" else "AI provider failure; human review required."
            return DecisionResult(WorkflowDecision.HUMAN_REVIEW, reason)
        if output.confidence < 0.85:
            return DecisionResult(WorkflowDecision.HUMAN_REVIEW, "Confidence below 0.85.")
        if output.category == RequestCategory.OTHER:
            return DecisionResult(WorkflowDecision.HUMAN_REVIEW, "Unclassified request requires human review.")
        if output.recommended_action == WorkflowDecision.HUMAN_REVIEW:
            return DecisionResult(WorkflowDecision.HUMAN_REVIEW, "Validated recommendation requires human review.")
        if output.category in (RequestCategory.MISSING_INFORMATION, RequestCategory.BILLING_QUESTION):
            return DecisionResult(WorkflowDecision.HUMAN_REVIEW, "Missing information and billing require human review.")
        if output.recommended_action == WorkflowDecision.REJECT and output.category != RequestCategory.DOCUMENT_PROCESSING:
            return DecisionResult(WorkflowDecision.HUMAN_REVIEW, "Automatic rejection is limited to document intake.")
        return DecisionResult(output.recommended_action, "Confidence and category satisfy administrative workflow rules.")
