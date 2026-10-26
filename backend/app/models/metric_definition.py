from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDMixin


class MetricDefinition(UUIDMixin, TimestampMixin, Base):
    """An approved, immutable calculation revision for one analysed dataset."""

    __tablename__ = "metric_definitions"
    __table_args__ = (
        UniqueConstraint("family_id", "version", name="uq_metric_definition_revision"),
        Index("ix_metric_definitions_analysis_current", "analysis_id", "is_current"),
        CheckConstraint("aggregation IN ('sum', 'average', 'count', 'distinct_count')", name="ck_metric_definition_aggregation"),
        CheckConstraint("version > 0", name="ck_metric_definition_version"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(24), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
