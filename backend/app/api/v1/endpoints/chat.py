from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser
from app.core.logging import get_logger
from app.models.analysis import Analysis
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import (
    ChatMessageResponse,
    ChatSessionResponse,
    CreateChatSessionRequest,
    SendMessageRequest,
)
from app.services.ai_service import AIService

router = APIRouter()
logger = get_logger(__name__)


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    current_user: CurrentUser,
    db: DB,
    analysis_id: uuid.UUID = Query(...),
):
    # Verify analysis belongs to user
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id, Analysis.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    sessions_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.analysis_id == analysis_id)
        .options(selectinload(ChatSession.messages))
        .order_by(ChatSession.created_at.desc())
    )
    sessions = sessions_result.scalars().all()

    return [
        ChatSessionResponse(
            id=s.id,
            analysis_id=s.analysis_id,
            title=s.title,
            message_count=len(s.messages),
            created_at=s.created_at,
            updated_at=s.updated_at,
            last_message=ChatMessageResponse.model_validate(s.messages[-1]) if s.messages else None,
        )
        for s in sessions
    ]


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateChatSessionRequest,
    current_user: CurrentUser,
    db: DB,
):
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == body.analysis_id, Analysis.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = ChatSession(
        analysis_id=body.analysis_id,
        title=body.title or "New conversation",
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    return ChatSessionResponse(
        id=session.id,
        analysis_id=session.analysis_id,
        title=session.title,
        message_count=0,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message=None,
    )


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def get_messages(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    # Verify session → analysis → user ownership
    session_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.analysis), selectinload(ChatSession.messages))
    )
    session = session_result.scalar_one_or_none()
    if not session or session.analysis.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = sorted(session.messages, key=lambda m: m.created_at)
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    current_user: CurrentUser,
    db: DB,
):
    # Verify session ownership
    session_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(
            selectinload(ChatSession.analysis).selectinload(Analysis.insights),
            selectinload(ChatSession.analysis).selectinload(Analysis.file),
            selectinload(ChatSession.messages),
        )
    )
    session = session_result.scalar_one_or_none()
    if not session or session.analysis.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    # Save user message
    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=body.content,
    )
    db.add(user_message)
    await db.flush()

    # Build conversation history for context
    history = [
        {"role": m.role, "content": m.content}
        for m in sorted(session.messages, key=lambda m: m.created_at)
    ]

    # Generate AI response
    ai_service = AIService()
    try:
        response = await ai_service.chat(
            analysis=session.analysis,
            history=history,
            user_message=body.content,
        )
        current_user.ai_queries_this_month = (current_user.ai_queries_this_month or 0) + 1
    except Exception as exc:
        logger.error("AI chat failed", exc=str(exc))
        response = {"content": "I encountered an error while processing your question. Please try again.", "chart_config": None}

    assistant_message = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=response["content"],
        chart_config=response.get("chart_config"),
        internal_metadata=response.get("metadata"),
    )
    db.add(assistant_message)
    await db.flush()
    await db.refresh(assistant_message)

    return ChatMessageResponse.model_validate(assistant_message)
