from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.chat_evidence import UNAVAILABLE, friendly_chat_content
from app.services.investigation import comparison_answer


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

    @model_validator(mode="before")
    @classmethod
    def present_audited_reply(cls, value: Any) -> Any:
        """Older audited replies also get plain wording, without rewriting history."""
        get = value.get if isinstance(value, dict) else lambda key, default=None: getattr(value, key, default)
        audit = get("internal_metadata") or {}
        if get("role") == "assistant" and isinstance(audit, dict) and audit.get("method") == "measured_chat_queries_v1":
            comparison = audit.get("comparison")
            if audit.get("status") == "succeeded" and isinstance(comparison, dict):
                comparison = {**comparison, "answer": comparison_answer(comparison)}
                content = comparison["answer"] + "\n\n" + comparison.get("scope", "")
                return {**{field: get(field) for field in cls.model_fields}, "comparison": comparison, "content": content}
            return {**{field: get(field) for field in cls.model_fields}, "comparison": None}
        if get("role") != "assistant" or not isinstance(audit, dict) or audit.get("method") != "measured_chat_facts_v1":
            return value
        if audit.get("status") == "succeeded" and isinstance(audit.get("facts"), list) and audit["facts"]:
            try:
                content = friendly_chat_content(audit["facts"])
            except (KeyError, TypeError, ValueError):
                return value
        elif audit.get("status") in {"failed", "unsupported"}:
            content = UNAVAILABLE
        else:
            return value
        return {**{field: get(field) for field in cls.model_fields}, "content": content}

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    chart_config: dict[str, Any] | None
    created_at: datetime
    comparison: dict[str, Any] | None = None
