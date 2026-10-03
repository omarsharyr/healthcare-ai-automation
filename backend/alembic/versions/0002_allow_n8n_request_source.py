"""Allow requests orchestrated by n8n without changing existing rows."""
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_requests_request_source"), "requests", type_="check")
    op.create_check_constraint(op.f("ck_requests_request_source"), "requests", "source IN ('api', 'n8n')")


def downgrade() -> None:
    # PostgreSQL rejects this downgrade if n8n rows exist, preserving their provenance.
    # Do not silently relabel or delete intake records to make a downgrade succeed.
    op.drop_constraint(op.f("ck_requests_request_source"), "requests", type_="check")
    op.create_check_constraint(op.f("ck_requests_request_source"), "requests", "source IN ('api')")
