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


class RequestCategory(str, Enum):
    CLAIM_STATUS = "CLAIM_STATUS"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    BILLING_QUESTION = "BILLING_QUESTION"
    DOCUMENT_PROCESSING = "DOCUMENT_PROCESSING"
    OTHER = "OTHER"
