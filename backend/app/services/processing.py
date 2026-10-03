import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.enums import RequestStatus, WorkflowDecision
from app.models import AuditEvent, HumanReview, Request
from app.schemas.processing import ProcessingResponse
from app.services.ai_provider import AIProvider
from app.services.errors import WorkflowError
from app.services.phi_redaction import PHIRedactionService
from app.services.request_classifier import RequestClassifier
from app.services.workflow_decision import WorkflowDecisionService

logger = logging.getLogger(__name__)


def audit(session: Session, request_id: int, event_type: str, metadata: dict[str, str] | None = None) -> None:
    session.add(AuditEvent(request_id=request_id, event_type=event_type, actor="system",
                           event_metadata=metadata or {}))


def processing_response(session: Session, request: Request) -> ProcessingResponse:
    response = ProcessingResponse.model_validate(request)
    response.review_id = session.scalar(select(HumanReview.id).where(HumanReview.request_id == request.id))
    return response


def process_request(session: Session, request_uuid: UUID, provider: AIProvider) -> ProcessingResponse:
    try:
        with session.begin():
            # Serialize processing of this request, including provider calls, for this synchronous MVP.
            try:
                request = session.scalar(select(Request).where(Request.request_uuid == request_uuid).with_for_update(nowait=True))
            except OperationalError as error:
                if getattr(error.orig, "sqlstate", None) == "55P03":
                    raise WorkflowError(409, "Request processing is already in progress") from None
                raise
            if request is None:
                raise WorkflowError(404, "Request not found")
            if request.status == RequestStatus.PROCESSED:
                return processing_response(session, request)
            if request.status != RequestStatus.RECEIVED:
                raise WorkflowError(409, "Request cannot be processed in its current state")
            redacted = PHIRedactionService().redact(request.request_text, request.patient_reference)
            audit(session, request.id, "PHI_REDACTION_COMPLETED", {key: str(value) for key, value in redacted.counts.items()})
            audit(session, request.id, "AI_CLASSIFICATION_STARTED")
            classification = RequestClassifier(provider).classify(redacted.text)
            if classification.output is None:
                audit(session, request.id, "AI_CLASSIFICATION_FAILED", {"reason_code": classification.failure or "provider_failure"})
            else:
                output = classification.output
                request.category = output.category
                request.confidence = output.confidence
                request.ai_recommendation = output.recommended_action
                audit(session, request.id, "AI_CLASSIFICATION_COMPLETED", {
                    "category": output.category.value, "confidence": str(output.confidence),
                    "recommendation": output.recommended_action.value,
                })
            decision = WorkflowDecisionService().decide(classification)
            request.system_decision = decision.decision
            request.decision_reason = decision.reason
            request.status = RequestStatus.PROCESSED
            audit(session, request.id, "WORKFLOW_DECISION_MADE", {"decision": decision.decision.value})
            if decision.decision == WorkflowDecision.HUMAN_REVIEW:
                session.add(HumanReview(request_id=request.id, ai_recommendation=request.ai_recommendation))
                audit(session, request.id, "HUMAN_REVIEW_REQUESTED")
            else:
                audit(session, request.id, "WORKFLOW_COMPLETED", {"decision": decision.decision.value})
            session.flush()
            response = processing_response(session, request)
        logger.info("workflow_processed")
        return response
    except WorkflowError:
        raise
    except Exception:
        # The failed transaction has rolled back. Record a safe terminal failure if DB access permits.
        logger.error("workflow_processing_failed")
        try:
            with session.begin():
                request = session.scalar(select(Request).where(Request.request_uuid == request_uuid).with_for_update())
                if request is not None and request.status == RequestStatus.RECEIVED:
                    request.status = RequestStatus.FAILED
                    request.decision_reason = "Internal workflow failure; manual investigation required."
                    audit(session, request.id, "WORKFLOW_FAILED", {"reason_code": "processing_failure"})
        except Exception:
            logger.error("workflow_failure_audit_unavailable")
        raise WorkflowError(500, "Request processing failed") from None
