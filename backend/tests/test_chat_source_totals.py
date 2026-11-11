"""Source counting instructions preserve one overall total or average."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services import ai_service as service
from app.services.ai_service import AIService
from tests.test_source_measure_comparison import analysis, source_fields


def stub_planner(monkeypatch, plan, prompts):
    async def create(**kwargs):
        prompts.append(kwargs["messages"][0]["content"])
        payload = {"answer_kind": "calculated", "plan": plan}
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    monkeypatch.setattr(service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))


@pytest.mark.parametrize("question", [
    "What is the total amount, counting each source_id once?",
    "What is the total amount, count every source record only once?",
    "What is the overall total amount? Every source record is counted exactly once.",
    "Give the total amount by counting each source_id just once.",
    "Give the total amount, using each source record once.",
])
async def test_source_once_instruction_produces_one_overall_total(tmp_path, monkeypatch, question):
    item = analysis(tmp_path)
    prompts = []
    stub_planner(monkeypatch, {"aggregation": "sum", "column": "amount", "group_by": "source_id"}, prompts)

    answer = await AIService().chat(item, [], question)

    assert answer["metadata"]["status"] == "succeeded"
    comparison = answer["metadata"]["comparison"]
    assert comparison["plan"]["group_by"] is None
    assert comparison["group_count"] == 1
    assert comparison["groups"][0]["value"] == 30
    assert comparison["aggregation_basis"]["entities"] == 3
    binding = answer["metadata"]["source_bindings"][0]
    assert binding["model_column"] == "source_id" and binding["bound_column"] is None
    assert "For one overall total or average" in prompts[0]


@pytest.mark.parametrize(("source", "key", "column", "question"), [
    ("Orders.csv", "orderid_related_2", "Freight", "What is the total order freight, counting each order once?"),
    ("Invoice.csv", "invoiceid_related_2", "Total", "What is the total Invoice Total, counting each InvoiceId once?"),
])
async def test_original_source_id_wording_does_not_request_a_group(tmp_path, monkeypatch, source, key, column, question):
    fields = source_fields((key,), source=source)
    fields[1]["measure_grain"]["source_column"] = column
    item = analysis(tmp_path, {key: ["001", "001", "002", "003", "003"], "amount": [5., 5., 5., 20., 20.],
                              "region": ["A", "A", "A", "B", "B"], "item": ["x", "x", "y", "x", "y"]}, fields)
    stub_planner(monkeypatch, {"aggregation": "sum", "column": "amount", "group_by": key}, [])

    answer = await AIService().chat(item, [], question)

    assert answer["metadata"]["comparison"]["groups"][0]["value"] == 30
    assert answer["metadata"]["comparison"]["plan"]["group_by"] is None


async def test_source_once_average_and_fact_filter_keep_their_requested_scope(tmp_path, monkeypatch):
    item = analysis(tmp_path)
    stub_planner(monkeypatch, {"aggregation": "average", "column": "amount", "group_by": "source_id",
        "filters": [{"column": "region", "op": "in", "values": ["A"]}], "order": "asc", "limit": 17}, [])

    answer = await AIService().chat(item, [], "What is the average amount in region A, counting each source_id once?")

    comparison = answer["metadata"]["comparison"]
    assert comparison["plan"]["group_by"] is None
    assert comparison["plan"]["aggregation"] == "average"
    assert comparison["plan"]["order"] == "asc" and comparison["plan"]["limit"] == 17
    assert comparison["plan"]["filters"][0]["column"] == "region"
    assert comparison["groups"][0]["value"] == 5
    assert comparison["aggregation_basis"]["entities"] == 2


@pytest.mark.parametrize("question", [
    "Show the total amount by source_id, counting each source record once.",
    "For each source_id, show the total amount, counting each source record once.",
    "Show the total amount per source_id, counting each source record once.",
    "Which source_id has the highest total amount, counting each source record once?",
    "Rank the source IDs by total amount, counting each source record once.",
    "Show the top source IDs for total amount, counting each source record once.",
    "Show every source ID's total amount, counting each source record once.",
    "Compare the total amounts, counting each source record once.",
    "Show a comparison of total amounts, counting each source record once.",
    "Show the distribution of total amount, counting each source record once.",
    "List the total amounts, counting each source record once.",
    "Show separate total amounts, counting each source record once.",
    "Show the amounts, counting each source record once.",
])
async def test_explicit_source_grouping_and_rankings_are_preserved(tmp_path, monkeypatch, question):
    item = analysis(tmp_path)
    stub_planner(monkeypatch, {"aggregation": "sum", "column": "amount", "group_by": "source_id"}, [])

    answer = await AIService().chat(item, [], question)

    assert answer["metadata"]["status"] == "succeeded"
    comparison = answer["metadata"]["comparison"]
    assert comparison["plan"]["group_by"] == "source_id" and comparison["group_count"] == 3
    assert comparison["groups"][0]["value"] == 20
    assert "source_bindings" not in answer["metadata"]


async def test_composite_parent_keys_deduplicate_the_whole_source_identity(tmp_path, monkeypatch):
    item = analysis(tmp_path, {"tenant": ["A", "A", "A", "B", "B"], "source_id": ["1", "1", "2", "1", "1"],
        "amount": [5., 5., 5., 20., 20.], "region": ["R"] * 5, "item": ["x"] * 5},
        source_fields(("tenant", "source_id")))
    stub_planner(monkeypatch, {"aggregation": "sum", "column": "amount", "group_by": "tenant"}, [])

    answer = await AIService().chat(item, [], "What is the total amount, counting each source record once?")

    comparison = answer["metadata"]["comparison"]
    assert comparison["plan"]["group_by"] is None
    assert comparison["groups"][0]["value"] == 30 and comparison["aggregation_basis"]["entities"] == 3


async def test_fact_measure_grouping_does_not_acquire_source_grain_correction(tmp_path, monkeypatch):
    fields = source_fields()
    fields[1]["measure_grain"] = {"kind": "fact", "repeated": False, "source_table": "entries.csv", "source_column": "amount"}
    item = analysis(tmp_path, fields=fields)
    stub_planner(monkeypatch, {"aggregation": "sum", "column": "amount", "group_by": "source_id"}, [])

    answer = await AIService().chat(item, [], "What is the total amount, counting each source_id once?")

    assert answer["metadata"]["comparison"]["plan"]["group_by"] == "source_id"
    assert "source_bindings" not in answer["metadata"]


async def test_main_fact_row_id_keeps_the_source_ambiguity_check(tmp_path, monkeypatch):
    fields = [*source_fields(), {"name": "row_id", "analysis_role": "identifier", "semantic_type": "identifier",
        "is_numeric": False, "is_date": False, "measure_grain": {"kind": "fact", "source_table": "entries.csv", "source_column": "row_id"}}]
    item = analysis(tmp_path, {"source_id": ["1", "1", "2"], "amount": [5., 5., 20.], "row_id": ["a", "b", "c"],
        "region": ["R"] * 3, "item": ["x"] * 3}, fields)
    stub_planner(monkeypatch, {"aggregation": "sum", "column": "amount", "group_by": "row_id"}, [])

    answer = await AIService().chat(item, [], "What is the total amount, counting each source_id once?")

    assert answer["metadata"]["status"] == "unsupported"
    assert "several selected groups" in answer["content"]
    assert "source_bindings" not in answer["metadata"]
