"""Add recommendation_feedback and the recommendation_calibration view

Revision ID: 003_recommendation_feedback
Revises: 002_add_share_token
Create Date: 2026-09-11 00:00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "003_recommendation_feedback"
down_revision: str | None = "002_add_share_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Per-source calibration from production feedback: how often owners found a
# recommendation helpful vs. the confidence it was shown with. Rows from
# recommendations generated before confidence_source existed group as 'unknown'.
CALIBRATION_VIEW_SQL = """
CREATE VIEW recommendation_calibration AS
SELECT
    COALESCE(confidence_source, 'unknown') AS confidence_source,
    COUNT(*) AS n,
    ROUND(AVG(confidence)::numeric, 4) AS mean_confidence,
    ROUND(AVG(CASE WHEN verdict = 'helpful' THEN 1.0 ELSE 0.0 END)::numeric, 4) AS helpful_rate,
    ROUND(
        AVG(POWER(confidence - CASE WHEN verdict = 'helpful' THEN 1.0 ELSE 0.0 END, 2))::numeric,
        4
    ) AS brier_score,
    MIN(created_at) AS first_feedback_at,
    MAX(created_at) AS last_feedback_at
FROM recommendation_feedback
GROUP BY COALESCE(confidence_source, 'unknown')
"""


def upgrade() -> None:
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("insight_id", UUID(as_uuid=True), sa.ForeignKey("insights.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("recommendation_title", sa.String(512), nullable=False),
        sa.Column("importance", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_source", sa.String(32), nullable=True),
        sa.Column("confidence_method", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("verdict IN ('helpful', 'not_helpful')", name="ck_recommendation_feedback_verdict"),
        sa.UniqueConstraint("insight_id", "user_id", name="uq_recommendation_feedback_insight_user"),
    )
    op.create_index("ix_recommendation_feedback_user_id", "recommendation_feedback", ["user_id"])
    op.create_index("ix_recommendation_feedback_analysis_id", "recommendation_feedback", ["analysis_id"])
    op.create_index(
        "ix_recommendation_feedback_confidence_source", "recommendation_feedback", ["confidence_source"]
    )
    op.execute(CALIBRATION_VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS recommendation_calibration")
    op.drop_index("ix_recommendation_feedback_confidence_source", table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_analysis_id", table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_user_id", table_name="recommendation_feedback")
    op.drop_table("recommendation_feedback")
