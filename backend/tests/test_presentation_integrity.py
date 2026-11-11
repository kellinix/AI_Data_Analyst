"""Chart completeness and stable contextual recommendation regressions."""
from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.analytics.chart_specs import build_visual_spec
from app.schemas.analysis import AnalysisDetailResponse, InsightResponse, SharedAnalysisResponse
from app.services.report_language import present_chart, present_insight, present_metadata


@pytest.mark.parametrize(("kind", "length", "names"), [
    ("line", 938, ["first", "second", "third"]),
    ("line", 1601, ["single"]),
    ("bar", 240, ["one", "two", "three", "four", "five", "six"]),
])
def test_visual_spec_keeps_every_selected_point_and_series(kind, length, names):
    options = {"xAxis": {"type": "category", "data": [str(index) for index in range(length)]},
        "yAxis": {"type": "value"},
        "series": [{"name": name, "type": kind, "data": [None if index == 5 else number * length + index
                    for index in range(length)]} for number, name in enumerate(names)]}
    if kind == "bar":
        options["_columns"] = {"x": "period", "y": "amount", "series_by": "group"}
    chart = {"type": kind, "xAxis": "period", "yAxis": "amount", "aggregation": "sum", "echarts_option": options}
    before = deepcopy(chart)

    spec = build_visual_spec(chart)
    encoded = json.loads(json.dumps(spec, allow_nan=False))

    rows = encoded["data"]["values"]
    label = "metric" if kind == "line" else "series"
    coordinate = "period" if kind == "line" else "category"
    assert len(rows) == length * len(names)
    assert Counter(row[label] for row in rows) == dict.fromkeys(names, length)
    for number, name in enumerate(names):
        selected = [row for row in rows if row[label] == name]
        assert [row[coordinate] for row in selected] == [str(index) for index in range(length)]
        assert [row["value"] for row in selected] == options["series"][number]["data"]
    assert chart == before


@pytest.mark.parametrize(("codes", "expected"), [
    (["G"], "The file calls this figure G. Its source guide is needed to explain the code."),
    (["G", "AB"], "The file calls these figures G and AB. Its source guide is needed to explain the codes."),
    (["G", "AB", "R"], "The file calls these figures G, AB and R. Its source guide is needed to explain the codes."),
])
def test_short_code_caption_uses_one_explanation_for_all_measures(codes, expected):
    names = [f"metric_{index}" for index in range(len(codes))]
    chart = {"type": "line", "xAxis": "date", "yAxis": names[0], "series": names,
        "echarts_option": {"xAxis": {"type": "category", "data": ["2025-01-01", "2025-02-01"]},
            "yAxis": {"type": "value"}, "series": [{"name": code, "data": [1, 2]} for code in codes],
            "_columns": {"x": "date", "ys": names, "aggregations": ["sum"] * len(codes)}}}
    metadata = {"schema": [{"name": name, "measure_grain": {"kind": "fact", "source_column": code}}
                           for name, code in zip(names, codes, strict=True)]}

    shown = present_chart(chart, metadata)

    assert expected in shown["description"]
    assert shown["description"].count("Its source guide is needed") == 1
    assert [series["data"] for series in shown["echarts_option"]["series"]] == [[1, 2]] * len(codes)
    assert present_chart(shown, metadata) == shown


def example():
    issue = {"column": "optional_value", "type": "missing_values", "affected_rows": 2, "severity": "critical",
             "description": "50.0% of values are missing; completeness alone does not establish whether this field is required"}
    original = {"type": "recommendation", "title": "Review high-impact data quality checks", "description": "Review",
        "importance": "high", "data": {"confidence_source": "rule:data_quality", "column": "optional_value",
            "evidence": "Optional value: " + issue["description"]}}
    metadata = {"data_quality": {"issues": [issue]}}
    return original, metadata


def test_contextual_recommendation_survives_presented_metadata_and_keeps_source_evidence():
    original, metadata = example()
    original_copy, metadata_copy = deepcopy(original), deepcopy(metadata)
    once = present_insight(original, metadata)
    displayed_metadata, _ = present_metadata(metadata, None)

    twice = present_insight(once, displayed_metadata)

    assert twice == once
    assert "blank optional value" in twice["title"]
    assert twice["data"]["source_evidence"] == original["data"]["evidence"]
    assert twice["data"]["supporting_figures"]["figures"][0]["value"] == 2
    assert original == original_copy and metadata == metadata_copy


def test_same_friendly_issue_description_does_not_bind_another_column():
    original, metadata = example()
    other = {**metadata["data_quality"]["issues"][0], "column": "other_value"}
    metadata["data_quality"]["issues"].insert(0, other)
    once = present_insight(original, metadata)
    displayed_metadata, _ = present_metadata(metadata, None)
    assert displayed_metadata["data_quality"]["issues"][0]["description"] == displayed_metadata["data_quality"]["issues"][1]["description"]

    twice = present_insight(once, displayed_metadata)

    assert "blank optional value" in twice["title"]
    assert "other value" not in twice["title"]
    assert twice["data"]["supporting_figures"]["basis"] == "Saved file check for optional value."
    assert twice["data"]["source_evidence"] == original["data"]["evidence"]


def test_ambiguous_same_column_fallback_keeps_general_advice():
    original, metadata = example()
    once = present_insight(original, metadata)
    displayed_metadata, _ = present_metadata(metadata, None)
    displayed_metadata["data_quality"]["issues"].append(deepcopy(displayed_metadata["data_quality"]["issues"][0]))

    twice = present_insight(once, displayed_metadata)

    assert twice["title"] == "Check the information behind these figures"
    assert twice["data"]["source_evidence"] == original["data"]["evidence"]


def test_owner_shared_and_export_wording_agree_after_repeated_model_validation():
    from app.api.v1.endpoints.analyses import _insight_dicts

    original, metadata = example()
    now, analysis_id = datetime.now(UTC), uuid4()
    saved = SimpleNamespace(**original, id=uuid4(), analysis_id=analysis_id, confidence=.8,
        chart_config=None, created_at=now, user_feedback=None, sort_order=200)
    owner = AnalysisDetailResponse(id=analysis_id, name="Example", status="completed", file_id=uuid4(),
        filename="example.csv", row_count=4, column_count=1, created_at=now, updated_at=now, summary=None,
        metadata=deepcopy(metadata), insights=[InsightResponse.model_validate(saved)])
    first = owner.insights[0].model_dump()
    owner = AnalysisDetailResponse.model_validate(owner)
    owner = AnalysisDetailResponse.model_validate(owner.model_dump())
    final = owner.insights[0].model_dump()
    exported = _insight_dicts(SimpleNamespace(insights=[saved], metadata_=metadata))[0]
    shared_insight = InsightResponse.model_validate(present_insight(InsightResponse.model_validate(saved).model_dump(), metadata))
    shared = SharedAnalysisResponse(name="Example", row_count=4, column_count=1, created_at=now,
        summary=None, insights=[shared_insight], charts=[])

    assert final["title"] == first["title"] == exported["title"] == shared.insights[0].title
    assert final["description"] == first["description"] == exported["description"] == shared.insights[0].description
    assert final["data"]["evidence"] == exported["data"]["evidence"] == shared.insights[0].data["evidence"]
    assert final["data"]["evidence_link"] == first["data"]["evidence_link"]
    assert final["data"]["supporting_figures"] == first["data"]["supporting_figures"] == exported["data"]["supporting_figures"]
    assert saved.title == original["title"] and saved.data == original["data"]
