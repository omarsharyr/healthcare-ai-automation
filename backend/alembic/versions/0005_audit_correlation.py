"""Attach opaque correlation IDs to workflow audits."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("correlation_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_audit_events_correlation_id"), "audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_correlation_id"), table_name="audit_events")
    op.drop_column("audit_events", "correlation_id")
