from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.analyses import download_profile_json, refresh_analysis_summary
from app.services.data_profile import _compact_kpi, _compact_numeric_stats
from app.services.summary_refresh import refresh_saved_summary


def _analysis():
    return SimpleNamespace(
        id=uuid.uuid4(), name="Sales", row_count=3, column_count=2, status="completed",
        summary="All regions are equally represented.",
        charts=[{"id": "chart-1"}],
        insights=[SimpleNamespace(type="summary", data={"column": "revenue", "value": 60, "is_total": True})],
        metadata_={
            "schema": [{"name": "revenue", "analysis_role": "metric"},
                       {"name": "region", "analysis_role": "dimension"}],
            "analysis_evidence": {"limitations": ["Existing scope note."]},
            "data_profile": {
                "columns": [{"name": "revenue", "numeric_summary": {"count": 3, "total": 60, "mean": 20}},
                            {"name": "region"}],
                "categories": {"region": {"top_values": [{"value": "North", "count": 2},
                                                         {"value": "South", "count": 1}]}},
                "dataset": {"sample_truncated": False},
            },
        },
    )


def test_legacy_summary_refresh_uses_saved_results_and_preserves_original():
    analysis = _analysis()
    original = analysis.summary
    response = refresh_saved_summary(analysis)
    assert "equally represented" not in response["summary"]
    assert "60 across 3 supplied values" in response["summary"]
    assert "66.7% of all 3" in response["summary"]
    assert analysis.metadata_["summary_previous"] == original
    assert analysis.metadata_["analysis_evidence"]["limitations"] == ["Existing scope note."]
    assert analysis.charts == [{"id": "chart-1"}]
    assert analysis.status == "completed"
    assert "previous_summary" not in analysis.metadata_["data_profile"]["analysis_evidence"]
    again = refresh_saved_summary(analysis)
    assert again == response
    assert analysis.metadata_["summary_previous"] == original


def test_old_profiles_cannot_silently_turn_weighted_values_into_plain_averages():
    analysis = _analysis()
    analysis.insights[0].data = {"column": "revenue", "value": 30, "is_total": False,
                                 "weighted_by": "units"}
    response = refresh_saved_summary(analysis)
    assert not any(fact["id"].startswith("metric_")
                   for fact in response["analysis_evidence"]["summary_checks"]["facts"])


def test_new_profiles_preserve_weighting_and_rate_units():
    stats = _compact_numeric_stats({"variance": {"mean": 80, "weighted_mean": 24,
                                                 "weight_column": "cost"}})
    assert stats["variance"]["weighted_mean"] == 24
    assert stats["variance"]["weight_column"] == "cost"
    kpi = _compact_kpi({"column": "variance", "value": 24, "weighted_by": "cost", "is_percent": True})
    assert kpi["weighted_by"] == "cost" and kpi["is_percent"]


def test_missing_saved_profile_requires_regeneration_instead_of_guessing():
    analysis = _analysis()
    analysis.metadata_ = {}
    original = analysis.summary
    with pytest.raises(ValueError, match="no saved data profile"):
        refresh_saved_summary(analysis)
    assert analysis.summary == original


async def test_summary_refresh_is_owner_scoped_and_does_not_restart_analysis():
    analysis = _analysis()
    owner = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=analysis))
    response = await refresh_analysis_summary(analysis.id, owner, db)
    assert "equally represented" not in response["summary"]
    statement = db.execute.call_args.args[0]
    assert set(statement.compile().params.values()) == {analysis.id, owner.id}
    assert analysis.status == "completed"
    db.flush.assert_awaited_once()


async def test_profile_download_uses_updated_saved_evidence_without_a_stale_file():
    analysis = _analysis()
    refresh_saved_summary(analysis)
    analysis.metadata_["profile_json_path"] = "/no-longer-current/profile.json"
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=analysis))
    response = await download_profile_json(analysis.id, SimpleNamespace(id=uuid.uuid4()), db)
    profile = json.loads(response.body)
    assert profile["analysis_evidence"]["summary_checks"]["method"] == "measured_facts_v1"


@pytest.mark.parametrize("value, status", [(None, 404), (SimpleNamespace(status="pending"), 409)])
async def test_summary_refresh_rejects_unavailable_or_unfinished_analysis(value, status):
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=value))
    with pytest.raises(HTTPException) as error:
        await refresh_analysis_summary(uuid.uuid4(), SimpleNamespace(id=uuid.uuid4()), db)
    assert error.value.status_code == status
    db.flush.assert_not_awaited()
