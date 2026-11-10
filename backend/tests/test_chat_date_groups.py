import json
from types import SimpleNamespace

import pytest

from app.services import ai_service
from app.services.ai_service import AIService, _requested_date_bucket


@pytest.mark.parametrize(("question", "expected"), [
    ("Which calendar year has the highest average reading?", "year"),
    ("What month had the most sales?", "month"),
    ("Show sales by calendar day", "day"),
    ("Count readings per year", "year"),
    ("Show each month", "month"),
    ("Average monthly income by department", None),
    ("Average income in 2025", None),
    ("Which department leads this year?", None),
])
def test_explicit_calendar_groups(question, expected):
    assert _requested_date_bucket(question) == expected


@pytest.mark.parametrize("planned_bucket", [None, "day"])
async def test_chat_honours_requested_year_over_timestamp_plan(monkeypatch, planned_bucket):
    plan = {"aggregation": "average", "column": "power_mw", "group_by": "timestamp",
            "date_bucket": planned_bucket}
    captured = []

    async def create(**kwargs):
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"answer_kind": "calculated", "plan": plan})))])

    async def compare(analysis, selected, **kwargs):
        captured.append(selected)
        return {"answer": "2007 has the highest average power.", "scope": "Based on recorded readings."}

    monkeypatch.setattr(ai_service, "client", SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(ai_service, "compare", compare)
    item = SimpleNamespace(row_count=2, column_count=2, insights=[], metadata_={"schema": [
        {"name": "power_mw", "analysis_role": "metric", "is_numeric": True},
        {"name": "timestamp", "analysis_role": "date", "is_date": True},
    ]})
    result = await AIService().chat(item, [], "Which calendar year has the highest average power?")
    assert result["metadata"]["status"] == "succeeded"
    assert captured[0].date_bucket == "year"
