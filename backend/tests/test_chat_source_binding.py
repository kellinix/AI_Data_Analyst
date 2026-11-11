"""Conservative source binding uses the actual Data Assistant entry point."""
from __future__ import annotations

import json
from types import SimpleNamespace

import polars as pl
import pytest

from app.services import ai_service as service
from app.services.ai_service import AIService


def dimension(name, table, column, semantic_type="country", **updates):
    return {"name": name, "analysis_role": "dimension", "semantic_type": semantic_type,
            "is_numeric": False, "is_date": False,
            "measure_grain": {"kind": "lookup", "repeated": True, "source_table": table, "source_column": column}, **updates}


def fields():
    return [{"name": "units", "dtype": "DOUBLE", "analysis_role": "metric", "semantic_type": "count", "is_numeric": True},
            dimension("customer_country", "Customer.csv", "Country"),
            dimension("billing_country", "Invoice.csv", "BillingCountry")]


def stub_planner(monkeypatch, selected):
    async def create(**kwargs):
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"answer_kind": "calculated", "plan": selected})))])

    monkeypatch.setattr(service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))


async def captured_plan(monkeypatch, schema, question, group_by="billing_country"):
    selected = {"aggregation": "sum", "column": "units", "group_by": group_by,
                "filters": [{"column": "record_status", "op": "in", "values": ["Completed"]}], "order": "asc", "limit": 17}
    stub_planner(monkeypatch, selected)
    seen = []

    async def compare(analysis, plan, **kwargs):
        seen.append(plan.model_dump())
        return {"answer": "Controlled result.", "scope": "Based on recorded rows.", "plan": plan.model_dump()}

    monkeypatch.setattr(service, "compare", compare)
    item = SimpleNamespace(row_count=3, column_count=len(schema), insights=[], metadata_={"schema": schema})
    answer = await AIService().chat(item, [], question)
    assert answer["metadata"]["status"] == "succeeded"
    return selected, seen[0], answer["metadata"]


async def test_customer_country_binding_changes_the_actual_result_when_billing_values_differ(tmp_path, monkeypatch):
    parquet = tmp_path / "joined.parquet"
    pl.DataFrame({"units": [1.0, 2.0, 10.0], "customer_country": ["A", "A", "B"],
                  "billing_country": ["X", "Y", "Y"]}).write_parquet(parquet)
    stub_planner(monkeypatch, {"aggregation": "sum", "column": "units", "group_by": "billing_country", "limit": 10})
    item = SimpleNamespace(id="source-binding", row_count=3, column_count=3, insights=[],
        file=SimpleNamespace(storage_path=str(parquet)), metadata_={"schema": fields()})
    raw_model_result = await service.compare(item, service.ComparisonPlan(aggregation="sum", column="units", group_by="billing_country"))
    assert raw_model_result["groups"][0]["value"] == 12

    answer = await AIService().chat(item, [], "Which customer country has the highest total units?")

    assert answer["metadata"]["status"] == "succeeded"
    result = answer["metadata"]["comparison"]
    assert result["plan"]["group_by"] == "customer_country"
    assert result["groups"][0]["group_value"] == "b"
    assert result["groups"][0]["value"] == 10
    assert answer["metadata"]["source_bindings"][0]["model_column"] == "billing_country"
    assert answer["metadata"]["source_bindings"][0]["bound_column"] == "customer_country"


@pytest.mark.parametrize(("table", "column", "question"), [
    ("Customer.csv", "Country", "Which customer country has the highest total units?"),
    ("Archive_Customers_2024-01-31.csv", "Country", "Which customers country has the highest total units?"),
    ("BusinessCustomers_2024_January.csv", "Country", "Which customer countries have the highest total units?"),
    ("DIM_Customers_2024_01_31.csv", "HomeRegion", "Which customers home_region has the highest total units?"),
    ("Customers_Data.csv", "HOMERegion", "Which Customer HomeRegion has the highest total units?"),
])
async def test_unambiguous_raw_table_and_attribute_tokens_bind_without_changing_other_plan_parts(monkeypatch, table, column, question):
    schema = fields()
    schema[1] = dimension("customer_country", table, column)
    original, actual, metadata = await captured_plan(monkeypatch, schema, question)

    assert actual["group_by"] == "customer_country"
    for name, value in original.items():
        if name != "group_by":
            assert actual[name] == value
    assert metadata["source_bindings"][0]["source_column"] == column


@pytest.mark.parametrize("modifier", ["Billing", "Shipping", "Birth"])
async def test_explicit_modifier_preserves_the_model_attribute(monkeypatch, modifier):
    schema = fields()
    schema[2] = dimension("billing_country", "Invoice.csv", f"{modifier}Country")
    _, actual, metadata = await captured_plan(monkeypatch, schema, f"Which customer {modifier.lower()} country has the highest total units?")

    assert actual["group_by"] == "billing_country"
    assert "source_bindings" not in metadata


@pytest.mark.parametrize("gap", ["current_table", "current_column", "candidate_table", "candidate_column"])
async def test_missing_original_provenance_keeps_the_model_plan(monkeypatch, gap):
    schema = fields()
    target = schema[2] if gap.startswith("current") else schema[1]
    target["measure_grain"].pop("source_table" if gap.endswith("table") else "source_column")
    _, actual, metadata = await captured_plan(monkeypatch, schema, "Which customer country has the highest total units?")

    assert actual["group_by"] == "billing_country"
    assert "source_bindings" not in metadata


async def test_two_matching_source_fields_remain_ambiguous(monkeypatch):
    schema = fields() + [dimension("other_customer_country", "EU_Customers.csv", "Country")]
    _, actual, metadata = await captured_plan(monkeypatch, schema, "Which customer country has the highest total units?")

    assert actual["group_by"] == "billing_country"
    assert "source_bindings" not in metadata


@pytest.mark.parametrize("difference", ["semantic_type", "analysis_role"])
async def test_semantic_and_role_differences_do_not_rebind(monkeypatch, difference):
    schema = fields()
    schema[1][difference] = "categorical_dimension" if difference == "semantic_type" else "attribute"
    _, actual, metadata = await captured_plan(monkeypatch, schema, "Which customer country has the highest total units?")

    assert actual["group_by"] == "billing_country"
    assert "source_bindings" not in metadata


@pytest.mark.parametrize("role", ["identifier", "dimension"])
async def test_recorded_id_rank_is_preserved_even_when_the_question_mentions_country(monkeypatch, role):
    schema = fields() + [dimension("customer_id", "Customer.csv", "CustomerID", analysis_role=role)]
    _, actual, metadata = await captured_plan(monkeypatch, schema, "Which customer ID from each country has the most units?", group_by="customer_id")

    assert actual["group_by"] == "customer_id"
    assert "source_bindings" not in metadata


async def test_explicit_complete_attribute_and_entity_are_both_required(monkeypatch):
    _, actual, metadata = await captured_plan(monkeypatch, fields(), "Which country has the highest total units?")

    assert actual["group_by"] == "billing_country"
    assert "source_bindings" not in metadata


async def test_partial_attribute_tokens_cannot_rebind(monkeypatch):
    schema = fields()
    schema[1] = dimension("customer_country", "Customer.csv", "HomeRegion")
    _, actual, metadata = await captured_plan(monkeypatch, schema, "Which customer region has the highest total units?")

    assert actual["group_by"] == "billing_country"
    assert "source_bindings" not in metadata


async def test_a_correct_model_binding_needs_no_correction_audit(monkeypatch):
    _, actual, metadata = await captured_plan(monkeypatch, fields(), "Which customer country has the highest total units?", group_by="customer_country")

    assert actual["group_by"] == "customer_country"
    assert "source_bindings" not in metadata
