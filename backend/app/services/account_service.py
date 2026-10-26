"""Server-side Supabase account management and local upload cleanup."""

import shutil
import uuid
from pathlib import Path

import httpx
from fastapi import HTTPException

from app.core.config import settings


async def confirm_auth_user(token: str, subject: str) -> None:
    """Do not auto-provision local accounts from deleted users' unexpired JWTs."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(503, "Authentication service is not configured")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
            )
    except httpx.RequestError:
        raise HTTPException(503, "Authentication service is unavailable") from None
    if response.status_code in (401, 403, 404):
        raise HTTPException(401, "Invalid or deleted account")
    if not response.is_success:
        raise HTTPException(503, "Authentication service is unavailable")
    try:
        user_id = response.json().get("id")
    except (ValueError, AttributeError):
        raise HTTPException(503, "Invalid authentication service response") from None
    if user_id != subject:
        raise HTTPException(401, "Invalid or deleted account")


async def delete_auth_user(subject: str) -> None:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "Account deletion is not configured")
    # Subjects come from verified JWTs; validate before inserting into a URL.
    subject = str(uuid.UUID(subject))
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(
                "DELETE",
                f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{subject}",
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                },
                json={"should_soft_delete": False},
            )
    except httpx.RequestError:
        raise HTTPException(503, "Account deletion service is unavailable; please retry") from None
    # A retry may follow a successful remote deletion and a local commit failure.
    if not response.is_success and response.status_code != 404:
        raise HTTPException(503, "Account deletion failed; please retry")


def delete_account_uploads(user_id: uuid.UUID) -> None:
    """Remove only this account's server-generated directory, including derived files."""
    root = Path(settings.upload_dir).resolve()
    directory = root / str(user_id)
    if directory.is_symlink() or directory.resolve().parent != root:
        raise ValueError("Account upload directory is outside the upload root")
    if directory.exists():
        shutil.rmtree(directory)
