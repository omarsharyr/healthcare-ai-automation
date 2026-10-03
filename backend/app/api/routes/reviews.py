from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.reviews import ReviewAction, ReviewRead
from app.services import reviews as review_service

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])
SessionDependency = Annotated[Session, Depends(get_session)]
ReviewId = Annotated[int, Path(gt=0)]


@router.get("/pending", response_model=list[ReviewRead])
def pending(session: SessionDependency, limit: Annotated[int, Query(ge=1, le=100)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0) -> list[ReviewRead]:
    return review_service.pending_reviews(session, limit, offset)


@router.post("/{review_id}/approve", response_model=ReviewRead)
def approve(review_id: ReviewId, session: SessionDependency, payload: ReviewAction | None = None) -> ReviewRead:
    return review_service.resolve_review(session, review_id, True, payload or ReviewAction())


@router.post("/{review_id}/reject", response_model=ReviewRead)
def reject(review_id: ReviewId, session: SessionDependency, payload: ReviewAction | None = None) -> ReviewRead:
    return review_service.resolve_review(session, review_id, False, payload or ReviewAction())
