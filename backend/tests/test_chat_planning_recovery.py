"""One bounded re-plan can recover a false refusal without guessing a query."""
from __future__ import annotations

import json
from types import SimpleNamespace

import polars as pl
import pytest

from app.services import ai_service as service
from app.services.ai_service import AIService


def response(payload, *, refusal=None):
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
                           choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload), refusal=refusal))])


def install_client(monkeypatch, payloads):
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return payloads[len(calls) - 1]

    monkeypatch.setattr(service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    return calls


def report(tmp_path):
    path = tmp_path / "submissions.parquet"
    pl.DataFrame({"score": [50., 100., 80.], "course_id": ["01", "01", "02"],
                  "duration": [234, 234, 269]}).write_parquet(path)
    origin = {"kind": "lookup", "repeated": True, "key_basis": "parent_primary",
              "source_table": "courses.csv", "entity_key_columns": ["course_id"]}
    fields = [{"name": "score", "dtype": "DOUBLE", "is_numeric": True, "is_date": False,
               "analysis_role": "metric", "semantic_type": "average_metric",
               "measure_grain": {"kind": "fact", "source_table": "submissions.csv", "source_column": "score"}},
              {"name": "course_id", "dtype": "VARCHAR", "is_numeric": False, "is_date": False,
               "analysis_role": "identifier", "semantic_type": "identifier",
               "measure_grain": {**origin, "source_column": "course_id"}},
              {"name": "duration", "dtype": "BIGINT", "is_numeric": True, "is_date": False,
               "analysis_role": "metric", "semantic_type": "numeric_metric",
               "measure_grain": {**origin, "source_column": "duration"}}]
    return SimpleNamespace(id="numeric-lookup-group", row_count=3, column_count=3, insights=[],
                           metadata_={"schema": fields}, file=SimpleNamespace(storage_path=str(path)))


async def test_recovery_executes_validated_fact_average_by_numeric_lookup(tmp_path, monkeypatch):
    valid = {"answer_kind": "calculated", "plan": {"aggregation": "average", "column": "score", "group_by": "duration"}}
    calls = install_client(monkeypatch, [response({"answer_kind": "unavailable", "fact_ids": []}), response(valid)])
    result = await AIService().chat(report(tmp_path), [], "Which duration has the highest average submission score?")
    assert result["metadata"]["status"] == "succeeded"
    assert result["metadata"]["comparison"]["groups"][0]["group_value"] == "269"
    assert result["metadata"]["comparison"]["groups"][0]["value"] == 80.
    assert result["metadata"]["planning_attempts"] == 2
    assert result["metadata"]["prompt_tokens"] == 200
    assert result["metadata"]["completion_tokens"] == 40
    assert len(calls) == 2
    repair = calls[1]["messages"][0]["content"]
    assert "Measured fact catalogue:" not in repair
    assert "Saved fields for calculation review:" in repair
    assert "recorded_categories" not in repair
    fields = json.loads(repair.split("\nSaved fields for calculation review:\n", 1)[1].split("\nRecorded table relationships:\n", 1)[0])
    assert len(fields) == 3
    assert set(fields[0]) == {"name", "role", "calculation_support", "aggregation_basis", "source_qualified_field", "source_role"}
    assert "missing_requirements" in calls[1]["messages"][-1]["content"]
    assert calls[1]["model"] == calls[0]["model"]


async def test_successful_first_plan_needs_no_recovery(tmp_path, monkeypatch):
    valid = {"answer_kind": "calculated", "plan": {"aggregation": "average", "column": "score"}}
    calls = install_client(monkeypatch, [response(valid)])
    result = await AIService().chat(report(tmp_path), [], "What is the average score?")
    assert result["metadata"]["status"] == "succeeded"
    assert result["metadata"]["planning_attempts"] == 1
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [
    {"answer_kind": "unavailable", "fact_ids": [], "missing_requirements": ["No recorded future revenue"]},
    {"answer_kind": "calculated", "plan": {"aggregation": "average", "column": "invented_revenue"}},
    {"answer_kind": "calculated", "plan": {"aggregation": "sum", "column": "course_id"}},
    {"answer_kind": "calculated", "plan": {"aggregation": "sum", "column": "score"}},
    {"answer_kind": "calculated", "plan": {"aggregation": "average", "column": "score", "sql": "SELECT 1"}},
])
async def test_recovery_cannot_bypass_query_safety(tmp_path, monkeypatch, payload):
    calls = install_client(monkeypatch, [response({"answer_kind": "unavailable", "fact_ids": []}), response(payload)])
    result = await AIService().chat(report(tmp_path), [], "Predict next year's revenue.")
    assert result["metadata"]["status"] == "unsupported"
    assert result["metadata"]["planning_attempts"] == 2
    assert "comparison" not in result["metadata"]
    assert len(calls) == 2


async def test_provider_refusal_is_never_replanned(tmp_path, monkeypatch):
    calls = install_client(monkeypatch, [response({"answer_kind": "unavailable", "fact_ids": []}, refusal="Provider refusal")])
    result = await AIService().chat(report(tmp_path), [], "A question")
    assert result["metadata"]["status"] == "unsupported"
    assert result["metadata"]["planning_attempts"] == 1
    assert len(calls) == 1


async def test_both_requests_share_one_timeout_budget(tmp_path, monkeypatch):
    valid = {"answer_kind": "calculated", "plan": {"aggregation": "average", "column": "score"}}
    install_client(monkeypatch, [response({"answer_kind": "unavailable", "fact_ids": []}), response(valid)])
    timeouts = []
    original = service.asyncio.wait_for

    async def record_timeout(awaitable, *, timeout):
        timeouts.append(timeout)
        if len(timeouts) == 1:
            await service.asyncio.sleep(.02)
        return await original(awaitable, timeout=timeout)

    monkeypatch.setattr(service.asyncio, "wait_for", record_timeout)
    result = await AIService().chat(report(tmp_path), [], "What is the average score?")
    assert result["metadata"]["status"] == "succeeded"
    assert len(timeouts) == 2
    assert timeouts[0] == service._AI_CHAT_TIMEOUT_SECONDS
    assert 0 < timeouts[1] < timeouts[0]


async def test_recovery_timeout_keeps_original_safe_refusal(tmp_path, monkeypatch):
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise TimeoutError
        return response({"answer_kind": "unavailable", "fact_ids": []})

    monkeypatch.setattr(service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result = await AIService().chat(report(tmp_path), [], "A question")
    assert result["metadata"]["status"] == "unsupported"
    assert result["metadata"]["planning_attempts"] == 2
    assert result["metadata"]["planning_recovery_error"] == "TimeoutError"
    assert len(calls) == 2
