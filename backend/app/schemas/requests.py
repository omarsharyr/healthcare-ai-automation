from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RequestSource(str, Enum):
    API = "api"


class RequestPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class AcceptanceStatus(str, Enum):
    ACCEPTED = "accepted"


class RequestCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    patient_reference: str = Field(min_length=1, max_length=64, pattern=r"^PAT-[0-9]+$")
    request_text: str = Field(min_length=10, max_length=10000)
    source: RequestSource = RequestSource.API
    priority: RequestPriority = RequestPriority.NORMAL


class RequestAccepted(BaseModel):
    request_id: UUID
    status: AcceptanceStatus = AcceptanceStatus.ACCEPTED
    persisted: bool = False
    message: str = "Request accepted for validation only; it has not been stored or queued for processing."
