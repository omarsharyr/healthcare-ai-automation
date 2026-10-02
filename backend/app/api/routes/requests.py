from fastapi import APIRouter, status

from app.schemas.requests import RequestAccepted, RequestCreate
from app.services.requests import accept_request

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])


@router.post("", response_model=RequestAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_request(request: RequestCreate) -> RequestAccepted:
    return accept_request(request)
