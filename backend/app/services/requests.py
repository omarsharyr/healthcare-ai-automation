from uuid import uuid4

from app.schemas.requests import RequestAccepted, RequestCreate


def accept_request(request: RequestCreate) -> RequestAccepted:
    """Acknowledge validated synthetic input without storing or processing it."""
    return RequestAccepted(request_id=uuid4())
