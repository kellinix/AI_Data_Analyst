"""Add owner-scoped, versioned metric definitions without changing saved analyses."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "005_metric_definitions"
down_revision: str | None = "004_completion_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metric_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("family_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("aggregation", sa.String(24), nullable=False),
        sa.Column("column_name", sa.String(512), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("family_id", "version", name="uq_metric_definition_revision"),
        sa.CheckConstraint("aggregation IN ('sum', 'average', 'count', 'distinct_count')", name="ck_metric_definition_aggregation"),
        sa.CheckConstraint("version > 0", name="ck_metric_definition_version"),
    )
    op.create_index("ix_metric_definitions_user_id", "metric_definitions", ["user_id"])
    op.create_index("ix_metric_definitions_analysis_current", "metric_definitions", ["analysis_id", "is_current"])


def downgrade() -> None:
    op.drop_table("metric_definitions")
