from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import RequestCategory, RequestStatus, WorkflowDecision


class ProcessingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    request_uuid: UUID
    category: RequestCategory | None
    confidence: float | None
    ai_recommendation: WorkflowDecision | None
    system_decision: WorkflowDecision | None
    decision_reason: str | None
    status: RequestStatus
    review_id: int | None = None
