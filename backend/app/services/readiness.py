import logging

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import AuditEvent, Request

logger = logging.getLogger(__name__)


def database_is_ready(session: Session) -> bool:
    try:
        session.execute(text("SELECT 1"))
        # Check migrated tables/permissions without loading patient data.
        session.execute(select(Request.id).limit(1))
        session.execute(select(AuditEvent.id).limit(1))
        return True
    except SQLAlchemyError:
        logger.warning("database_not_ready")
        return False
