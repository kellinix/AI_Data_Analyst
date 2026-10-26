from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDMixin


class ExportEvent(UUIDMixin, Base):
    """A generated export; this does not prove the browser saved the download."""

    __tablename__ = "export_events"
    __table_args__ = (CheckConstraint("format IN ('pdf', 'excel')", name="ck_export_events_format"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), index=True,
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    exported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
