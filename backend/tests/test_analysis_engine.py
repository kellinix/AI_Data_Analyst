from __future__ import annotations

import pytest

from app.services import analysis_engine
from app.services.analysis_engine import AnalysisEngine


class _RecordingSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __aenter__(self) -> _RecordingSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def commit(self) -> None:
        self.calls.append("commit")

    async def rollback(self) -> None:
        self.calls.append("rollback")


async def test_failed_pipeline_rolls_back_before_marking_the_analysis_failed(monkeypatch):
    """Regression: after a failed flush the session is unusable until rolled
    back. Without the rollback, _mark_failed raised PendingRollbackError and the
    analysis stayed "processing" forever instead of showing its error."""
    session = _RecordingSession()
    monkeypatch.setattr(analysis_engine, "AsyncSessionLocal", lambda: session)
    engine = AnalysisEngine()

    async def failing_pipeline(db, analysis_id):
        raise TypeError("Object of type date is not JSON serializable")

    async def mark_failed(db, analysis_id, error):
        session.calls.append(f"mark_failed: {error}")

    monkeypatch.setattr(engine, "_run_pipeline", failing_pipeline)
    monkeypatch.setattr(engine, "_mark_failed", mark_failed)

    with pytest.raises(TypeError):
        await engine.run("00000000-0000-0000-0000-000000000000")

    assert session.calls == [
        "rollback",
        "mark_failed: Object of type date is not JSON serializable",
        "commit",
    ]
