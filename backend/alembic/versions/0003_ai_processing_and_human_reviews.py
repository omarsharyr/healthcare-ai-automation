"""Persist AI decisions and transactional human review state."""
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def decision_enum(name: str) -> sa.Enum:
    return sa.Enum("AUTO_PROCESS", "HUMAN_REVIEW", "REJECT", name=name,
                   native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_requests_request_status"), "requests", type_="check")
    op.alter_column("requests", "status", existing_type=sa.String(8), type_=sa.String(9), existing_nullable=False)
    op.create_check_constraint(op.f("ck_requests_request_status"), "requests", "status IN ('received', 'processed', 'failed')")
    op.add_column("requests", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("requests", sa.Column("ai_recommendation", sa.String(12), nullable=True))
    op.add_column("requests", sa.Column("system_decision", sa.String(12), nullable=True))
    op.add_column("requests", sa.Column("decision_reason", sa.String(500), nullable=True))
    op.create_check_constraint(op.f("ck_requests_confidence_range"), "requests", "confidence >= 0 AND confidence <= 1")
    for column in ("ai_recommendation", "system_decision"):
        op.create_check_constraint(op.f(f"ck_requests_{column}"), "requests",
                                   f"{column} IN ('AUTO_PROCESS', 'HUMAN_REVIEW', 'REJECT')")
    op.create_table(
        "human_reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "APPROVED", "REJECTED", name="review_status", native_enum=False, create_constraint=True), server_default="PENDING", nullable=False),
        sa.Column("ai_recommendation", decision_enum("review_ai_recommendation"), nullable=True),
        sa.Column("reviewer_decision", decision_enum("reviewer_decision"), nullable=True),
        sa.Column("reviewer_notes", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_reviews")),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="RESTRICT", name=op.f("fk_human_reviews_request_id_requests")),
        sa.UniqueConstraint("request_id", name=op.f("uq_human_reviews_request_id")),
        sa.CheckConstraint(
            "(status = 'PENDING' AND reviewer_decision IS NULL AND reviewed_at IS NULL) OR "
            "(status = 'APPROVED' AND reviewer_decision IS NOT NULL AND reviewer_decision = 'AUTO_PROCESS' AND reviewed_at IS NOT NULL) OR "
            "(status = 'REJECTED' AND reviewer_decision IS NOT NULL AND reviewer_decision = 'REJECT' AND reviewed_at IS NOT NULL)",
            name=op.f("ck_human_reviews_review_resolution"),
        ),
    )
    op.create_index(op.f("ix_human_reviews_status"), "human_reviews", ["status"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM requests WHERE status <> 'received')")):
        raise RuntimeError("Cannot downgrade while processed or failed requests exist")
    op.drop_index(op.f("ix_human_reviews_status"), table_name="human_reviews")
    op.drop_table("human_reviews")
    for name in ("confidence_range", "ai_recommendation", "system_decision"):
        op.drop_constraint(op.f(f"ck_requests_{name}"), "requests", type_="check")
    for column in ("decision_reason", "system_decision", "ai_recommendation", "confidence"):
        op.drop_column("requests", column)
    op.drop_constraint(op.f("ck_requests_request_status"), "requests", type_="check")
    op.alter_column("requests", "status", existing_type=sa.String(9), type_=sa.String(8), existing_nullable=False)
    op.create_check_constraint(op.f("ck_requests_request_status"), "requests", "status IN ('received')")
