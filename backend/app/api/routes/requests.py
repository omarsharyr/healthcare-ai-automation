from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.requests import RequestCreate, RequestCreated, RequestRead
from app.services import requests as request_service
from app.services.ai_provider import AIProvider, get_ai_provider
from app.services.processing import process_request
from app.schemas.processing import ProcessingResponse

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])


SessionDependency = Annotated[Session, Depends(get_session)]


@router.post("", response_model=RequestCreated, status_code=status.HTTP_201_CREATED)
def create_request(request: RequestCreate, response: Response, session: SessionDependency) -> RequestCreated:
    created = request_service.create_request(session, request)
    response.headers["Location"] = f"/api/v1/requests/{created.request_uuid}"
    return created


@router.get("/{request_uuid}", response_model=RequestRead)
def get_request(request_uuid: UUID, session: SessionDependency) -> RequestRead:
    request = request_service.get_request(session, request_uuid)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return request


@router.post("/{request_uuid}/process", response_model=ProcessingResponse)
def process(request_uuid: UUID, session: SessionDependency,
            provider: Annotated[AIProvider, Depends(get_ai_provider)]) -> ProcessingResponse:
    return process_request(session, request_uuid, provider)
