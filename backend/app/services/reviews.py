from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ReviewStatus, WorkflowDecision
from app.models import AuditEvent, HumanReview, Request
from app.schemas.reviews import ReviewAction, ReviewRead
from app.services.errors import WorkflowError


def review_response(review: HumanReview, request: Request) -> ReviewRead:
    return ReviewRead(id=review.id, request_uuid=request.request_uuid, status=review.status,
                      ai_recommendation=review.ai_recommendation, reviewer_decision=review.reviewer_decision,
                      reviewer_notes=review.reviewer_notes, created_at=review.created_at, reviewed_at=review.reviewed_at)


def pending_reviews(session: Session, limit: int, offset: int) -> list[ReviewRead]:
    rows = session.execute(select(HumanReview, Request).join(Request, Request.id == HumanReview.request_id)
                           .where(HumanReview.status == ReviewStatus.PENDING)
                           .order_by(HumanReview.created_at, HumanReview.id).limit(limit).offset(offset)).all()
    return [review_response(review, request) for review, request in rows]


def resolve_review(session: Session, review_id: int, approve: bool, payload: ReviewAction) -> ReviewRead:
    with session.begin():
        review = session.scalar(select(HumanReview).where(HumanReview.id == review_id).with_for_update())
        if review is None:
            raise WorkflowError(404, "Review not found")
        if review.status != ReviewStatus.PENDING:
            raise WorkflowError(409, "Review has already been completed")
        request = session.scalar(select(Request).where(Request.id == review.request_id).with_for_update())
        if request is None or request.system_decision != WorkflowDecision.HUMAN_REVIEW:
            raise WorkflowError(409, "Request is not awaiting review")
        review.status = ReviewStatus.APPROVED if approve else ReviewStatus.REJECTED
        review.reviewer_decision = WorkflowDecision.AUTO_PROCESS if approve else WorkflowDecision.REJECT
        review.reviewer_notes = payload.reviewer_notes
        review.reviewed_at = datetime.now(timezone.utc)
        request.system_decision = review.reviewer_decision
        request.decision_reason = "Human reviewer approved workflow." if approve else "Human reviewer rejected workflow."
        for event_type in ("HUMAN_REVIEW_COMPLETED", "WORKFLOW_COMPLETED"):
            session.add(AuditEvent(request_id=request.id, event_type=event_type, actor="human_reviewer",
                                  event_metadata={"decision": review.reviewer_decision.value, "review_id": str(review.id)}))
        session.flush()
        response = review_response(review, request)
    return response
