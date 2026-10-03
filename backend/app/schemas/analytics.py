from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.core.enums import RequestCategory, RequestStatus


class AnalyticsFilters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    category: RequestCategory | None = None
    status: RequestStatus | None = None

    @model_validator(mode="after")
    def valid_dates(self) -> "AnalyticsFilters":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Start date must not follow end date")
        if self.date_to == date.max:
            raise ValueError("End date is out of range")
        return self


class AnalyticsSummary(BaseModel):
    total_requests: int
    completed_requests: int
    pending_requests: int
    automated: int
    human_reviews: int
    pending_reviews: int
    failures: int
    automation_rate: float
    average_ai_confidence: float | None
    requests_by_category: dict[str, int]
    requests_by_decision: dict[str, int]
    requests_by_status: dict[str, int]
    agent_executions: int
    agent_failures: int
    agent_tool_calls: int
    agent_tool_rejections: int
    agent_tool_usage: dict[str, int]
    ai_failures: int


class ActivityItem(BaseModel):
    event_id: int
    created_at: datetime
    event_type: str
    actor: str
    correlation_id: UUID | None
    run_uuid: UUID | None


class ActivityResponse(BaseModel):
    items: list[ActivityItem]
