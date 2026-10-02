from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Request
from app.schemas.requests import RequestCreate, RequestCreated, RequestRead


def create_request(session: Session, payload: RequestCreate) -> RequestCreated:
    """Commit request and audit together, or roll both back on any failure."""
    with session.begin():
        request = Request(**payload.model_dump())
        session.add(request)
        session.flush()
        session.add(AuditEvent(
            request_id=request.id,
            event_type="REQUEST_RECEIVED",
            actor="api",
            event_metadata={"source": payload.source.value, "priority": payload.priority.value},
        ))
        session.flush()
        response = RequestCreated.model_validate(request)
    return response


def get_request(session: Session, request_uuid: UUID) -> RequestRead | None:
    request = session.scalar(select(Request).where(Request.request_uuid == request_uuid))
    return RequestRead.model_validate(request) if request is not None else None
