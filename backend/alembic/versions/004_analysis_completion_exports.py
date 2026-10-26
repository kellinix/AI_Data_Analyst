"""Record analysis completion and generated exports.

Historical completion times stay NULL: updated_at may reflect a later rename.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "004_completion_exports"
down_revision: str | None = "003_recommendation_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "export_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("format IN ('pdf', 'excel')", name="ck_export_events_format"),
    )
    op.create_index("ix_export_events_analysis_id", "export_events", ["analysis_id"])


def downgrade() -> None:
    op.drop_table("export_events")
    op.drop_column("analyses", "completed_at")
