from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from app.core.config import settings


def configure_logging() -> None:
    """Configure structured JSON logging for production, pretty for development."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if settings.debug else logging.INFO,
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.debug else logging.INFO
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Suppress noisy loggers in production
    if settings.is_production:
        for name in ("uvicorn.access", "sqlalchemy.engine"):
            logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    return structlog.get_logger(name)


logger = get_logger(__name__)
