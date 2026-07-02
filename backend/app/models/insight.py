from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis


class Insight(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "insights"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Arbitrary insight-type-specific data (evidence, KPIs, opportunity size, etc.)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Linked chart config (optional)
    chart_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    analysis: Mapped[Analysis] = relationship("Analysis", back_populates="insights")

    def __repr__(self) -> str:
        return f"<Insight id={self.id} type={self.type} title={self.title[:40]}>"
