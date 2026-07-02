from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis


class SubscriptionPlan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Supabase Auth UID (mirrors auth.users.id)
    supabase_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    plan: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SubscriptionPlan.FREE.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Monthly usage counters (reset on billing cycle)
    analyses_this_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_queries_this_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_used_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    analyses: Mapped[list["Analysis"]] = relationship(
        "Analysis", back_populates="user", cascade="all, delete-orphan"
    )
    subscription: Mapped["Subscription | None"] = relationship(
        "Subscription", back_populates="user", uselist=False
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
