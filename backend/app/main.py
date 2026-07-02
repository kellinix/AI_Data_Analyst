from __future__ import annotations

import time
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import engine

configure_logging()
logger = get_logger(__name__)

# Sentry
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1 if settings.is_production else 1.0,
    )

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up", environment=settings.environment)
    yield
    logger.info("Shutting down")
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    openapi_url="/api/openapi.json" if not settings.is_production else None,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# Request logging + timing
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    request_id = request.headers.get("X-Request-ID", "")
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "Unhandled exception",
            method=request.method,
            path=request.url.path,
            exc=str(exc),
        )
        raise
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "Request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration_ms, 1),
        request_id=request_id,
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration_ms:.1f}ms"
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error", error=str(exc), path=request.url.path)
    content = {"detail": "An internal error occurred"}
    if not settings.is_production:
        content["error"] = str(exc)

    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=content,
    )
    origin = request.headers.get("origin")
    if origin and ("*" in settings.cors_origins or origin in settings.cors_origins):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


# Include routes
app.include_router(api_router, prefix="/api/v1")
