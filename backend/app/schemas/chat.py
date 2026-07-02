from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateChatSessionRequest(BaseModel):
    analysis_id: uuid.UUID
    title: str | None = None


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    last_message: ChatMessageResponse | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4096)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    chart_config: dict[str, Any] | None
    created_at: datetime
