from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.enums import RequestCategory, RequestStatus
from app.db.session import get_session
from app.schemas.analytics import ActivityResponse, AnalyticsFilters, AnalyticsSummary
from app.services import analytics

router = APIRouter(prefix='/api/v1/analytics', tags=['analytics'])


def get_filters(date_from: date | None = None, date_to: date | None = None,
                category: RequestCategory | None = None, status: RequestStatus | None = None) -> AnalyticsFilters:
    try:
        return AnalyticsFilters(date_from=date_from, date_to=date_to, category=category, status=status)
    except ValidationError:
        raise HTTPException(422, 'Invalid date range') from None


@router.get('/summary', response_model=AnalyticsSummary)
def summary(session: Annotated[Session, Depends(get_session)],
            filters: Annotated[AnalyticsFilters, Depends(get_filters)]) -> AnalyticsSummary:
    return analytics.summary(session, filters)


@router.get('/activity', response_model=ActivityResponse)
def activity(session: Annotated[Session, Depends(get_session)], filters: Annotated[AnalyticsFilters, Depends(get_filters)],
             limit: Annotated[int, Query(ge=1, le=100)] = 30) -> ActivityResponse:
    return analytics.activity(session, filters, limit)
