from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import RequestCategory, RequestStatus, WorkflowDecision, ReviewStatus


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgentRun(StrictInput):
    message: str = Field(min_length=3, max_length=4000)
    request_uuid: UUID | None = None


class RequestToolInput(StrictInput):
    request_uuid: UUID


class DocumentsInput(StrictInput):
    category: RequestCategory


class EscalationInput(RequestToolInput):
    # Controlled reason code, never persisted free-form model text.
    reason: Literal["USER_REQUESTED", "UNCERTAIN", "AGENT_FAILURE"]


class EmptyInput(StrictInput):
    pass


class ToolCall(StrictInput):
    name: str = Field(min_length=1, max_length=80)
    arguments: str = Field(max_length=2000, description="JSON object matching the selected tool input schema")


class AgentPlan(StrictInput):
    intent: Literal["lookup", "documents", "review", "unsupported"]
    calls: list[ToolCall] = Field(max_length=20)


class StatusOutput(BaseModel):
    request_uuid: UUID
    status: RequestStatus
    category: RequestCategory | None
    system_decision: WorkflowDecision | None


class HistoryOutput(BaseModel):
    request_uuid: UUID
    event_types: list[str]
    truncated: bool


class DocumentsOutput(BaseModel):
    category: RequestCategory
    documents: list[str]
    synthetic_policy: bool = True


class ReviewOutput(BaseModel):
    review_id: int
    status: ReviewStatus
    created: bool


class CountOutput(BaseModel):
    pending_count: int


class ToolResult(BaseModel):
    tool: str
    output: StatusOutput | HistoryOutput | DocumentsOutput | ReviewOutput | CountOutput


class AgentResponse(BaseModel):
    run_uuid: UUID
    response: str
    tools_used: list[str]
    results: list[ToolResult]
    escalated: bool
    human_action_required: bool
    status: Literal["completed", "fallback"]
