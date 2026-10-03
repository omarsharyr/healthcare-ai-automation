from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import RequestCategory, WorkflowDecision


class AIClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, str_strip_whitespace=True)

    category: RequestCategory
    confidence: float = Field(ge=0, le=1)
    recommended_action: WorkflowDecision
    reason: str = Field(min_length=1, max_length=500)
