from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ReviewStatus, WorkflowDecision


class ReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reviewer_notes: str | None = Field(default=None, max_length=2000)


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    request_uuid: UUID
    status: ReviewStatus
    ai_recommendation: WorkflowDecision | None
    reviewer_decision: WorkflowDecision | None
    reviewer_notes: str | None
    created_at: datetime
    reviewed_at: datetime | None
