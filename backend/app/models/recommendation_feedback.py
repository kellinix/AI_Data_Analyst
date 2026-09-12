from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDMixin

FEEDBACK_VERDICTS = ("helpful", "not_helpful")


class RecommendationFeedback(UUIDMixin, TimestampMixin, Base):
    """An owner's verdict on one recommendation — the production outcome signal
    for confidence calibration.

    Insights are deleted and regenerated on every re-run, so `insight_id` is
    nulled then (ON DELETE SET NULL). The snapshot columns keep each verdict
    joinable to the confidence that was actually shown. Deleting the analysis
    or the user deletes their feedback.
    """

    __tablename__ = "recommendation_feedback"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('helpful', 'not_helpful')",
            name="ck_recommendation_feedback_verdict",
        ),
        UniqueConstraint("insight_id", "user_id", name="uq_recommendation_feedback_insight_user"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    insight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)

    # Snapshot of the recommendation at feedback time.
    recommendation_title: Mapped[str] = mapped_column(String(512), nullable=False)
    importance: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_source: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    confidence_method: Mapped[str | None] = mapped_column(String(16), nullable=True)

    def __repr__(self) -> str:
        return f"<RecommendationFeedback insight={self.insight_id} verdict={self.verdict}>"
