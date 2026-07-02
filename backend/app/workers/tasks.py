from __future__ import annotations

import asyncio
import uuid

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from app.core.logging import configure_logging, get_logger
from app.workers.celery_app import celery_app

configure_logging()
logger = get_logger(__name__)


async def _mark_analysis_failed(analysis_id: str, error: str) -> None:
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.analysis import Analysis, AnalysisStatus

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Analysis).where(Analysis.id == uuid.UUID(analysis_id)))
        analysis = result.scalar_one_or_none()
        if analysis:
            analysis.status = AnalysisStatus.FAILED.value
            analysis.error_message = error[:1024]
            await db.commit()


class AsyncTask(Task):
    """Base task class that runs async tasks in a new event loop."""

    def run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            try:
                from app.db.session import engine

                loop.run_until_complete(engine.dispose())
            except Exception as exc:
                logger.warning("Failed to dispose async DB engine", exc=str(exc))
            loop.close()


@celery_app.task(
    bind=True,
    base=AsyncTask,
    name="run_analysis",
    queue="analysis",
    max_retries=3,
    default_retry_delay=30,
)
def run_analysis_task(self: AsyncTask, analysis_id: str) -> dict:
    """
    Celery task that runs the full analysis pipeline.
    Async code is executed in a dedicated event loop.
    """
    logger.info("Analysis task started", analysis_id=analysis_id, task_id=self.request.id)

    try:
        from app.services.analysis_engine import AnalysisEngine

        engine = AnalysisEngine()
        self.run_async(engine.run(analysis_id))
        logger.info("Analysis task completed", analysis_id=analysis_id)
        return {"status": "completed", "analysis_id": analysis_id}

    except SoftTimeLimitExceeded:
        logger.error("Analysis timed out", analysis_id=analysis_id)
        self.run_async(_mark_analysis_failed(analysis_id, "Analysis timed out"))
        return {"status": "failed", "error": "Analysis timed out"}

    except Exception as exc:
        logger.error("Analysis task failed", analysis_id=analysis_id, exc=str(exc))
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            return {"status": "failed", "error": str(exc)}
