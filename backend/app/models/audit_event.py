from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.correlation import current_correlation_id


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("requests.id", ondelete="RESTRICT"), index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True, default=current_correlation_id)
    # DeclarativeBase reserves 'metadata'; keep the requested SQL column name.
    event_metadata: Mapped[dict[str, str]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
