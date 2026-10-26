"""Idempotent operational accounting while legacy quotas remain in force."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_event import UsageEvent


def _token_count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**31 else None


async def reserve_analysis(db: AsyncSession, *, user_id: uuid.UUID, analysis_id: uuid.UUID) -> None:
    statement = pg_insert(UsageEvent).values(
        user_id=user_id, kind="analysis", resource_id=analysis_id,
        status="reserved", source="live", occurred_at=datetime.now(UTC),
    ).on_conflict_do_nothing(constraint="uq_usage_event_resource")
    await db.execute(statement)


async def finalize_analysis(
    db: AsyncSession, *, user_id: uuid.UUID, analysis_id: uuid.UUID,
    status: str, created_at: datetime,
) -> None:
    if status not in {"completed", "failed"}:
        raise ValueError("Analysis usage can only finish as completed or failed")
    now = datetime.now(UTC)
    statement = pg_insert(UsageEvent).values(
        user_id=user_id, kind="analysis", resource_id=analysis_id,
        status=status, source="live", occurred_at=created_at, completed_at=now,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_usage_event_resource",
        set_={
            "status": case(
                (UsageEvent.status == "completed", "completed"),
                else_=statement.excluded.status,
            ),
            "completed_at": case(
                (UsageEvent.status == "completed", UsageEvent.completed_at),
                else_=statement.excluded.completed_at,
            ),
        },
    )
    await db.execute(statement)


async def record_chat_response(
    db: AsyncSession, *, user_id: uuid.UUID, message_id: uuid.UUID,
    metadata: dict[str, Any] | None,
) -> None:
    metadata = metadata or {}
    succeeded = metadata.get("status") == "succeeded"
    now = datetime.now(UTC)
    statement = pg_insert(UsageEvent).values(
        user_id=user_id, kind="ai_followup", resource_id=message_id,
        status="completed" if succeeded else "failed", source="live",
        occurred_at=now, completed_at=now,
        model=str(metadata["model"])[:128] if metadata.get("model") else None,
        prompt_tokens=_token_count(metadata.get("prompt_tokens")),
        completion_tokens=_token_count(metadata.get("completion_tokens")),
    ).on_conflict_do_nothing(constraint="uq_usage_event_resource")
    await db.execute(statement)
