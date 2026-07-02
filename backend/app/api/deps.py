from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_supabase_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate the Supabase JWT, then fetch or create the local user."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_supabase_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    supabase_id: str | None = payload.get("sub")
    if not supabase_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Fetch user from local DB
    result = await db.execute(select(User).where(User.supabase_id == supabase_id))
    user = result.scalar_one_or_none()

    if user is None:
        # Auto-provision user on first login
        email = payload.get("email") or f"{supabase_id}@supabase.local"
        user_metadata = payload.get("user_metadata", {})
        email_result = await db.execute(select(User).where(User.email == email))
        user = email_result.scalar_one_or_none()

        if user is None:
            user = User(
                supabase_id=supabase_id,
                email=email,
                full_name=user_metadata.get("full_name"),
                avatar_url=user_metadata.get("avatar_url"),
                is_verified=payload.get("email_confirmed_at") is not None,
            )
            db.add(user)
        else:
            user.supabase_id = supabase_id
            user.full_name = user.full_name or user_metadata.get("full_name")
            user.avatar_url = user.avatar_url or user_metadata.get("avatar_url")

        await db.flush()
        await db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[AsyncSession, Depends(get_db)]
