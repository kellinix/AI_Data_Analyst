from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis


class ChatSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="New conversation")

    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )

    @property
    def message_count(self) -> int:
        return len(self.messages)


class ChatMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chart_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Internal metadata (SQL query used, tokens consumed, etc.)
    internal_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
