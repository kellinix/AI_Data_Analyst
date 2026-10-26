"""Persist immutable dashboard layout revisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "006_dashboard_revisions"
down_revision: str | None = "005_metric_definitions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dashboard_revisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("analysis_id", "version", name="uq_dashboard_revision_version"),
        sa.CheckConstraint("version > 0", name="ck_dashboard_revision_version"),
    )
    op.create_index("ix_dashboard_revisions_analysis_id", "dashboard_revisions", ["analysis_id"])


def downgrade() -> None:
    op.drop_table("dashboard_revisions")
