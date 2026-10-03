from enum import Enum


class RequestSource(str, Enum):
    API = "api"
    N8N = "n8n"


class RequestPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class RequestStatus(str, Enum):
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"


class WorkflowDecision(str, Enum):
    AUTO_PROCESS = "AUTO_PROCESS"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REJECT = "REJECT"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RequestCategory(str, Enum):
    CLAIM_STATUS = "CLAIM_STATUS"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    BILLING_QUESTION = "BILLING_QUESTION"
    DOCUMENT_PROCESSING = "DOCUMENT_PROCESSING"
    OTHER = "OTHER"
