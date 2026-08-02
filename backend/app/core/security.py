from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Supabase projects created after JWT signing keys rolled out sign access
# tokens with an asymmetric key (ES256/RS256) verified via JWKS, not the
# legacy shared HS256 secret. Cache the key set — it changes only on manual
# rotation — instead of fetching it on every request.
_JWKS_CACHE_TTL_SECONDS = 3600
_jwks_cache: dict[str, Any] = {"fetched_at": 0.0, "keys": []}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode JWT token. Raises JWTError on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


async def _get_jwks() -> list[dict[str, Any]]:
    now = time.monotonic()
    if now - _jwks_cache["fetched_at"] < _JWKS_CACHE_TTL_SECONDS and _jwks_cache["keys"]:
        return _jwks_cache["keys"]

    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
        response.raise_for_status()
        keys = response.json().get("keys", [])

    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


async def verify_supabase_token(token: str) -> dict[str, Any]:
    """Verify a Supabase JWT, signature always checked, in every environment.

    Accepting unverified claims in "non-production" mode is a full auth
    bypass if environment detection is ever misconfigured — fail closed
    instead. Supabase supports two signing modes depending on project
    configuration: the legacy shared HS256 secret, and JWKS-based asymmetric
    signing (ES256/RS256) that newer projects default to. Branch on the
    token's declared algorithm rather than assuming HS256.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise ValueError(f"Invalid Supabase token header: {e}") from e

    algorithm = header.get("alg")

    if algorithm == "HS256":
        if not settings.supabase_jwt_secret:
            raise ValueError("SUPABASE_JWT_SECRET is not configured")
        try:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except JWTError as e:
            raise ValueError(f"Invalid Supabase token: {e}") from e

    if algorithm in ("ES256", "RS256"):
        if not settings.supabase_url:
            raise ValueError("SUPABASE_URL is not configured")
        kid = header.get("kid")
        try:
            keys = await _get_jwks()
        except httpx.HTTPError as e:
            raise ValueError(f"Could not fetch Supabase JWKS: {e}") from e

        matching_key = next((k for k in keys if k.get("kid") == kid), None)
        if matching_key is None:
            raise ValueError(f"No matching JWKS key for kid={kid}")

        try:
            return jwt.decode(
                token,
                matching_key,
                algorithms=[algorithm],
                options={"verify_aud": False},
            )
        except JWTError as e:
            raise ValueError(f"Invalid Supabase token: {e}") from e

    raise ValueError(f"Unsupported Supabase token algorithm: {algorithm}")
