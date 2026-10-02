from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.readiness import database_is_ready

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}})
def ready(response: Response, session: Annotated[Session, Depends(get_session)]) -> ReadinessResponse:
    response.headers["Cache-Control"] = "no-store"
    if database_is_ready(session):
        return ReadinessResponse(status="ready", database="ok")
    response.status_code = 503
    return ReadinessResponse(status="not_ready", database="unavailable")
