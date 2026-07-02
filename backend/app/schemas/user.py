from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None
    avatar_url: str | None = None


class UserCreate(UserBase):
    supabase_id: str


class UserUpdate(BaseModel):
    full_name: str | None = None
    avatar_url: str | None = None


class UsageStats(BaseModel):
    analyses_this_month: int
    analyses_limit: int
    storage_used_bytes: int
    storage_limit_bytes: int
    ai_queries_this_month: int
    ai_queries_limit: int


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserProfileResponse(UserResponse):
    subscription: Any | None = None
    usage: UsageStats
