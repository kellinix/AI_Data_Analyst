from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "ai_dashboard",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_default_queue="default",
    task_routes={
        "run_analysis": {"queue": "analysis"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.analysis_timeout_seconds,
    task_time_limit=settings.analysis_timeout_seconds + 60,
    task_max_retries=settings.celery_max_retries,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)
