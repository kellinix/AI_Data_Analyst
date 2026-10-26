from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.db.session import engine

router = APIRouter()


@router.get("")
async def health_check(response: Response):
    """Health check endpoint for load balancers."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    if db_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "database": db_status,
    }
