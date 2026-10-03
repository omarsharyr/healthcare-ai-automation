"""Allow global agent audits without an invented healthcare request."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("audit_events", "request_id", existing_type=sa.BigInteger(), nullable=True)


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM audit_events WHERE request_id IS NULL)")):
        raise RuntimeError("Cannot downgrade while global audit events exist")
    op.alter_column("audit_events", "request_id", existing_type=sa.BigInteger(), nullable=False)
