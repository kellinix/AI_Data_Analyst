from __future__ import annotations

import pytest

from app.services import analysis_engine
from app.services.analysis_engine import AnalysisEngine, consolidated_anomaly_card


def test_a_single_anomaly_keeps_its_own_title():
    title, description = consolidated_anomaly_card(
        [{"title": "Standout Cost", "description": "One record reached 5,118.30 for Cost."}]
    )

    assert title == "Standout Cost"
    assert description == "One record reached 5,118.30 for Cost."


def test_several_anomalies_become_one_card():
    """Regression: five "Standout <measure>" cards each said a single record
    was higher than almost every other record — the same sentence five times."""
    anomalies = [
        {"title": "Standout Cost", "description": "One record reached 5,118.30 for Cost."},
        {"title": "Standout Variance", "description": "One record reached 733.00 for Variance."},
        {"title": "Standout Benefits", "description": "One record reached 40,967.00 for Benefits."},
    ]

    title, description = consolidated_anomaly_card(anomalies)

    assert title == "Standout records in 3 measures"
    assert description.startswith("One record reached 5,118.30 for Cost.")
    assert description.endswith("Single records also stand out in Variance and Benefits.")


def test_only_money_charts_are_tagged_with_the_currency():
    statistics = {
        "schema": [
            {"name": "whole_life_cost", "semantic_type": "currency"},
            {"name": "project_count", "semantic_type": "numeric_metric"},
            {"name": "department", "semantic_type": "department"},
        ]
    }
    charts = [
        {"xAxis": "whole_life_cost", "yAxis": "department", "series": ["whole_life_cost"]},
        {"xAxis": "project_count", "yAxis": "department", "series": ["project_count"]},
    ]

    analysis_engine._tag_currency_charts(charts, statistics, {"code": "GBP", "symbol": "£"})

    assert charts[0]["currency"] == "GBP"
    assert "currency" not in charts[1]


def test_charts_are_untouched_when_the_currency_is_unknown():
    charts = [{"xAxis": "cost", "yAxis": "department", "series": ["cost"]}]

    analysis_engine._tag_currency_charts(charts, {"schema": [{"name": "cost", "semantic_type": "currency"}]}, None)

    assert "currency" not in charts[0]


def test_currency_comes_from_the_cleaning_report_first():
    """Cleaning sees the original header "(£m)" before standardisation rewrites
    the symbol, so its report is the authoritative source."""
    upload_context = {"cleaning": {"report": {"currency": {"code": "GBP", "symbol": "£"}}}}
    statistics = {"schema": [{"name": "revenue_usd"}]}

    assert analysis_engine._resolve_currency(statistics, upload_context) == {"code": "GBP", "symbol": "£"}


def test_currency_falls_back_to_column_names_on_the_raw_path():
    statistics = {"schema": [{"name": "project"}, {"name": "Financial Year Baseline (£m)"}]}

    resolved = analysis_engine._resolve_currency(statistics, None)

    assert resolved["code"] == "GBP"
    assert resolved["symbol"] == "£"


def test_currency_stays_unknown_when_nothing_says_so():
    statistics = {"schema": [{"name": "revenue"}, {"name": "region"}]}

    assert analysis_engine._resolve_currency(statistics, {"cleaning": {"report": {}}}) is None


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
