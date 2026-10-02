"""Create requests and audit events.

Revision ID: 0001
Revises: None
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("request_uuid", sa.Uuid(), nullable=False),
        sa.Column("patient_reference", sa.String(64), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("source", sa.Enum("api", name="request_source", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("priority", sa.Enum("low", "normal", "high", name="request_priority", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("status", sa.Enum("received", name="request_status", native_enum=False, create_constraint=True), server_default="received", nullable=False),
        sa.Column("category", sa.Enum("CLAIM_STATUS", "MISSING_INFORMATION", "BILLING_QUESTION", "DOCUMENT_PROCESSING", "OTHER", name="request_category", native_enum=False, create_constraint=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("char_length(request_text) BETWEEN 10 AND 10000", name=op.f("ck_requests_request_text_length")),
        sa.CheckConstraint("patient_reference ~ '^PAT-[0-9]+$'", name=op.f("ck_requests_patient_reference_format")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requests")),
        sa.UniqueConstraint("request_uuid", name=op.f("uq_requests_request_uuid")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], name=op.f("fk_audit_events_request_id_requests"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_request_id"), "audit_events", ["request_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_request_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("requests")
