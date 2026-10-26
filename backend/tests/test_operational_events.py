import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.v1.endpoints import analyses
from app.models.export_event import ExportEvent
from app.services.analysis_engine import AnalysisEngine


async def test_successful_analysis_records_completion_time():
    analysis = SimpleNamespace(
        id=uuid.uuid4(), user_id=uuid.uuid4(), created_at=datetime.now(UTC),
        completed_at=None,
    )
    db = AsyncMock()
    db.add = Mock()
    engine = AnalysisEngine.__new__(AnalysisEngine)
    before = datetime.now(UTC)
    await engine._persist_results(
        db=db, analysis=analysis, row_count=10, column_count=2,
        summary="Ready", charts=[], kpis=[], ai_insights=[], ai_recommendations=[], metadata={},
    )
    assert analysis.status == "completed"
    assert before <= analysis.completed_at <= datetime.now(UTC)
    assert analysis.completed_at.tzinfo == UTC


@pytest.mark.parametrize("format", ["pdf", "excel"])
async def test_export_records_only_successful_generation(monkeypatch, format):
    analysis = SimpleNamespace(
        id=uuid.uuid4(), name="Sales", row_count=10, column_count=2, summary="Ready", insights=[],
        charts=[{"type": "line", "title": "Revenue"}], metadata_={},
    )
    monkeypatch.setattr(analyses, "_load_analysis_for_export", AsyncMock(return_value=analysis))
    builder = Mock(return_value=b"report")
    monkeypatch.setattr(analyses, f"build_{format}_report", builder)
    db = AsyncMock()
    db.add = Mock()
    route = getattr(analyses, f"export_{format}")
    response = await route(analysis.id, SimpleNamespace(id=uuid.uuid4()), db)
    assert response.body == b"report"
    assert builder.call_args.kwargs["charts"] == analysis.charts
    [event] = db.add.call_args.args
    assert isinstance(event, ExportEvent)
    assert event.analysis_id == analysis.id
    assert event.format == format
    db.flush.assert_awaited_once()

    db.add.reset_mock()
    builder.side_effect = ValueError("cannot generate report")
    with pytest.raises(ValueError):
        await route(analysis.id, SimpleNamespace(id=uuid.uuid4()), db)
    db.add.assert_not_called()


async def test_rerun_clears_previous_completion(monkeypatch):
    analysis = SimpleNamespace(id=uuid.uuid4(), completed_at=datetime.now(UTC), insights=[])
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=analysis))
    monkeypatch.setattr(analyses, "_regenerate_cleaned_file_for_rerun", AsyncMock(return_value=None))
    monkeypatch.setattr(analyses.run_analysis_task, "delay", Mock(return_value=SimpleNamespace(id="test-task")))
    monkeypatch.setattr(analyses, "_analysis_detail_response", Mock(return_value={}))
    await analyses.rerun_analysis.__wrapped__(None, analysis.id, SimpleNamespace(id=uuid.uuid4()), db)
    assert analysis.status == "pending"
    assert analysis.completed_at is None
