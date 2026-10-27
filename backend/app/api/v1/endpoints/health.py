from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.logging import get_logger
from app.db.session import engine

router = APIRouter()
logger = get_logger(__name__)


def _database_error_types(exc: Exception) -> list[str]:
    """Report exception classes without logging connection credentials or SQL text."""
    types = []
    seen = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        types.append(type(current).__name__)
        current = getattr(current, "orig", None) or current.__cause__
    return types


@router.get("")
async def health_check(response: Response):
    """Health check endpoint for load balancers."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        logger.warning("Database health check failed", error_types=_database_error_types(exc))
        db_status = "error"

    if db_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "database": db_status,
    }
