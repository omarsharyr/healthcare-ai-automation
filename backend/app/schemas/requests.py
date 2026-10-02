from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


from app.core.enums import RequestCategory, RequestPriority, RequestSource, RequestStatus


class RequestCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    patient_reference: str = Field(min_length=1, max_length=64, pattern=r"^PAT-[0-9]+$")
    request_text: str = Field(min_length=10, max_length=10000)
    source: RequestSource = RequestSource.API
    priority: RequestPriority = RequestPriority.NORMAL


class RequestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_uuid: UUID
    source: RequestSource
    priority: RequestPriority
    status: RequestStatus
    category: RequestCategory | None
    created_at: datetime
    updated_at: datetime


class RequestCreated(RequestSummary):
    persisted: Literal[True] = True
    message: str = "Request stored with an audit event; no processing has been queued."


class RequestRead(RequestSummary):
    patient_reference: str
    request_text: str
