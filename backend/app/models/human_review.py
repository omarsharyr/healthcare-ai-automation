from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ReviewStatus, WorkflowDecision
from app.db.base import Base
from app.models.request import enum_values


class HumanReview(Base):
    __tablename__ = "human_reviews"
    __table_args__ = (
        CheckConstraint(
            "(status = 'PENDING' AND reviewer_decision IS NULL AND reviewed_at IS NULL) OR "
            "(status = 'APPROVED' AND reviewer_decision IS NOT NULL AND reviewer_decision = 'AUTO_PROCESS' AND reviewed_at IS NOT NULL) OR "
            "(status = 'REJECTED' AND reviewer_decision IS NOT NULL AND reviewer_decision = 'REJECT' AND reviewed_at IS NOT NULL)",
            name="review_resolution",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="RESTRICT"), unique=True)
    status: Mapped[ReviewStatus] = mapped_column(Enum(
        ReviewStatus, values_callable=enum_values, native_enum=False, create_constraint=True,
        name="review_status", validate_strings=True,
    ), default=ReviewStatus.PENDING, server_default="PENDING", index=True)
    ai_recommendation: Mapped[WorkflowDecision | None] = mapped_column(Enum(
        WorkflowDecision, values_callable=enum_values, native_enum=False, create_constraint=True,
        name="review_ai_recommendation", validate_strings=True,
    ), nullable=True)
    reviewer_decision: Mapped[WorkflowDecision | None] = mapped_column(Enum(
        WorkflowDecision, values_callable=enum_values, native_enum=False, create_constraint=True,
        name="reviewer_decision", validate_strings=True,
    ), nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
