from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, Float, Identity, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import RequestCategory, RequestPriority, RequestSource, RequestStatus, WorkflowDecision
from app.db.base import Base


def enum_values(enum_class: type[PythonEnum]) -> list[str]:
    return [member.value for member in enum_class]


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        CheckConstraint("char_length(request_text) BETWEEN 10 AND 10000", name="request_text_length"),
        CheckConstraint("patient_reference ~ '^PAT-[0-9]+$'", name="patient_reference_format"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    request_uuid: Mapped[UUID] = mapped_column(Uuid, default=uuid4, unique=True)
    patient_reference: Mapped[str] = mapped_column(String(64))
    request_text: Mapped[str] = mapped_column(Text)
    source: Mapped[RequestSource] = mapped_column(Enum(
        RequestSource, values_callable=enum_values, native_enum=False,
        create_constraint=True, name="request_source", validate_strings=True,
    ))
    priority: Mapped[RequestPriority] = mapped_column(Enum(
        RequestPriority, values_callable=enum_values, native_enum=False,
        create_constraint=True, name="request_priority", validate_strings=True,
    ))
    status: Mapped[RequestStatus] = mapped_column(Enum(
        RequestStatus, values_callable=enum_values, native_enum=False,
        create_constraint=True, name="request_status", validate_strings=True,
    ), default=RequestStatus.RECEIVED, server_default="received")
    category: Mapped[RequestCategory | None] = mapped_column(Enum(
        RequestCategory, values_callable=enum_values, native_enum=False,
        create_constraint=True, name="request_category", validate_strings=True,
    ), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_recommendation: Mapped[WorkflowDecision | None] = mapped_column(Enum(
        WorkflowDecision, values_callable=enum_values, native_enum=False, create_constraint=True,
        name="ai_recommendation", validate_strings=True,
    ), nullable=True)
    system_decision: Mapped[WorkflowDecision | None] = mapped_column(Enum(
        WorkflowDecision, values_callable=enum_values, native_enum=False, create_constraint=True,
        name="system_decision", validate_strings=True,
    ), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
