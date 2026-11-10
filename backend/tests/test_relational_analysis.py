from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import duckdb
import polars as pl
import pytest

from app.analytics.statistics import StatisticsEngine
from app.services.file_processor import FileProcessor
from app.services.investigation import (
    ComparisonPlan,
    ComparisonUnavailable,
    EntryRequest,
    RelationshipUnavailable,
    compare,
    entries,
    validate_plan,
)


def sourced(frame, name):
    return frame.with_columns(pl.lit(name).alias("Source file"))


def combine(frames, context=None):
    context = context if context is not None else {"combine_strategy": "portfolio"}
    return FileProcessor()._combine_frames(frames, context), context


def test_lookup_enrichment_preserves_every_transaction_and_amount():
    donors = sourced(pl.DataFrame({"donor_id": ["D1", "D2", "D3"], "segment": ["High Value", "Mid-Level", "Other"]}), "donors.csv")
    gifts = sourced(pl.DataFrame({"gift_id": ["G1", "G2", "G3", "G4"],
        "donor_id": ["D1", "D1", "D2", "missing"], "amount_usd": [100, 200, 30, 40]}), "gifts.csv")
    result, context = combine([donors, gifts])
    assert result.height == 4
    assert result["gift_id"].to_list() == ["G1", "G2", "G3", "G4"]
    assert result["amount_usd"].sum() == 370
    assert result["segment"].to_list() == ["High Value", "High Value", "Mid-Level", None]
    assert context["combine_strategy"] == "relational"
    [join] = context["relationship_resolution"]["joins"]
    assert join["matched_entries"] == 3 and join["unmatched_entries"] == 1
    assert join["lookup_only_entries"] == 1


@pytest.mark.parametrize("entity", ["customer_id", "patient_id", "product_key", "employee_code"])
def test_relationships_are_industry_independent_and_file_order_independent(entity):
    lookup = sourced(pl.DataFrame({entity: ["A", "B"], "category": ["First", "Second"]}), "entities.csv")
    facts = sourced(pl.DataFrame({entity: ["A", "A", "B"], "value": [2, 3, 4]}), "events.csv")
    for frames in ([lookup, facts], [facts, lookup]):
        result, _ = combine(frames)
        assert result["category"].to_list() == ["First", "First", "Second"]
        assert result["value"].to_list() == [2, 3, 4]


def test_partitions_and_multiple_lookup_tables_keep_event_grain():
    first = sourced(pl.DataFrame({"customer_id": ["A", "A"], "product_id": ["P", "Q"], "value": [2, 3]}), "first.csv")
    second = sourced(pl.DataFrame({"customer_id": ["B"], "product_id": ["P"], "value": [4]}), "second.csv")
    customers = sourced(pl.DataFrame({"customer_id": ["A", "B"], "region": ["UK", "US"]}), "customers.csv")
    products = sourced(pl.DataFrame({"product_id": ["P", "Q"], "name": ["One", "Two"]}), "products.csv")
    result, _ = combine([customers, first, products, second])
    assert result.height == 3 and result["value"].sum() == 9
    assert result["region"].to_list() == ["UK", "UK", "US"]
    assert result["name"].to_list() == ["One", "Two", "One"]
    assert result["Source file"].to_list() == ["first.csv", "first.csv", "second.csv"]


def test_safe_key_normalization_preserves_leading_zeros_and_overlapping_fields():
    lookup = sourced(pl.DataFrame({"Customer ID": ["001", "1"], "status": ["VIP", "Standard"]}), "customers.csv")
    facts = sourced(pl.DataFrame({"customer_id": [" 001 ", "001", "1"], "status": ["Paid"] * 3,
        "status related 1": ["existing"] * 3}), "orders.csv")
    result, context = combine([lookup, facts])
    assert result["status"].to_list() == ["Paid"] * 3
    renamed = context["relationship_resolution"]["joins"][0]["renamed_fields"]["status"]
    assert renamed != "status related 1"
    assert result[renamed].to_list() == ["VIP", "VIP", "Standard"]


@pytest.mark.parametrize("lookup_keys", [["A", "A"], ["A", None], ["A", " A "], ["X", "Y"]])
def test_ambiguous_duplicate_null_or_nonmatching_keys_are_not_joined(lookup_keys):
    lookup = sourced(pl.DataFrame({"customer_id": lookup_keys, "region": ["UK", "US"]}), "customers.csv")
    facts = sourced(pl.DataFrame({"customer_id": ["A", "A", "B"], "value": [2, 3, 4]}), "orders.csv")
    result, context = combine([lookup, facts])
    assert result.height == 5 and result["value"].sum() == 9
    assert context["relationship_resolution"]["status"] == "unresolved"


def test_explicit_unsafe_join_does_not_aggregate_away_transaction_detail():
    left = sourced(pl.DataFrame({"customer_id": ["A", "A"], "amount": [1, 2]}), "one.csv")
    right = sourced(pl.DataFrame({"customer_id": ["A", "A"], "cost": [3, 4]}), "two.csv")
    result, _ = combine([left, right], {"combine_strategy": "join", "suggestions": [{"type": "join", "columns": ["customer_id"]}]})
    assert result.height == 4
    assert result["amount"].sum() == 3 and result["cost"].sum() == 7


async def make_analysis(tmp_path, frame, context=None):
    path = tmp_path / f"{uuid4()}.parquet"
    frame.write_parquet(path)
    conn = duckdb.connect(":memory:")
    try:
        await FileProcessor().read_to_duckdb_ex(conn, str(path), ".parquet")
        statistics = StatisticsEngine(conn).describe_all()
    finally:
        conn.close()
    return SimpleNamespace(id=uuid4(), file=SimpleNamespace(storage_path=str(path)),
        row_count=frame.height, metadata_={**statistics, "upload_context": context or {}}, insights=[])


@pytest.fixture
async def activity(tmp_path):
    return await make_analysis(tmp_path, pl.DataFrame({
        "customer_id": ["A", "A", "B", "C", "A", "A", "B", "D", None, "unknown", ""],
        "event_date": [date(2024, 1, 1)] * 4 + [date(2025, 1, 1)] * 7,
        "status": ["Completed"] * 6 + ["Refunded"] + ["Completed"] * 4,
        "amount": [10.] * 11,
    }))


def retention(**overrides):
    return ComparisonPlan(**{
        "aggregation": "retention", "column": "customer_id",
        "filters": [{"column": "status", "op": "in", "values": ["Completed"]}],
        "cohort_filters": [{"column": "event_date", "op": "date_between", "values": ["2024-01-01", "2024-12-31"]}],
        "return_filters": [{"column": "event_date", "op": "date_between", "values": ["2025-01-01", "2025-12-31"]}],
        **overrides,
    })


async def test_retention_uses_distinct_entities_and_filters_both_periods(activity):
    result = await compare(activity, retention())
    assert result["cohort"] == {"baseline_entities": 3, "returning_entities": 1}
    assert result["groups"][0]["value"] == pytest.approx(100 / 3)
    assert "1 of 3" in result["answer"] and "33.3%" in result["answer"]
    drilldown = await entries(activity, EntryRequest(kind="comparison", comparison=retention(), evidence_revision=result["evidence_revision"]))
    assert drilldown["matched_entries"] == 4
    assert {row["values"]["customer_id"] for row in drilldown["entries"]} == {"A", "B", "C"}
    assert "only once" in drilldown["scope"]


async def test_zero_baseline_is_unavailable_and_sampling_is_qualified(activity):
    plan = retention(cohort_filters=[{"column": "event_date", "op": "date_between", "values": ["2020-01-01", "2020-12-31"]}])
    activity.metadata_["data_profile"] = {"dataset": {"sample_truncated": True, "row_count": 11}}
    result = await compare(activity, plan)
    assert result["groups"][0]["value"] is None
    assert "unavailable" in result["answer"] and "first 11" in result["scope"]


@pytest.mark.parametrize("overrides", [
    {"cohort_filters": []}, {"return_filters": []}, {"group_by": "status"},
    {"column": "amount"}, {"weight_column": "amount"},
    {"return_filters": [{"column": "missing", "op": "in", "values": ["A"]}]},
    {"return_filters": [{"column": "event_date", "op": "date_between", "values": ["2025-12-31", "2025-01-01"]}]},
])
async def test_invalid_retention_plans_are_rejected(activity, overrides):
    with pytest.raises(ValueError):
        validate_plan(retention(**overrides), activity.metadata_)


async def test_cohort_values_are_parameters_and_cannot_inject_sql(activity):
    result = await compare(activity, retention(filters=[{"column": "status", "op": "in", "values": ["Completed' OR 1=1 --"]}]))
    assert result["cohort"]["baseline_entities"] == 0


async def test_disconnected_portfolio_does_not_claim_zero_matches(tmp_path):
    frame = pl.DataFrame({"customer_id": ["A", "A", "A"], "segment": ["VIP", None, None], "amount": [None, 10., 20.]})
    analysis = await make_analysis(tmp_path, frame, {"combined": True, "combine_strategy": "portfolio"})
    plan = ComparisonPlan(aggregation="sum", column="amount", filters=[{"column": "segment", "op": "in", "values": ["VIP"]}])
    with pytest.raises(RelationshipUnavailable, match="separate record types"):
        await compare(analysis, plan)
    with pytest.raises(RelationshipUnavailable):
        await entries(analysis, EntryRequest(kind="comparison", comparison=plan))


async def test_real_zero_on_a_valid_combination_remains_zero_matches(activity):
    activity.metadata_["upload_context"] = {"combined": True, "combine_strategy": "portfolio"}
    result = await compare(activity, ComparisonPlan(aggregation="sum", column="amount",
        filters=[{"column": "status", "op": "in", "values": ["Does not exist"]}]))
    assert result["matched_entries"] == 0


async def test_chat_executes_retention_and_ignores_model_numbers(activity, monkeypatch):
    import json

    from app.services import ai_service

    async def create(**kwargs):
        assert "cohort_filters" in kwargs["messages"][0]["content"]
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "answer_kind": "calculated", "plan": retention().model_dump(), "answer": "99.9%",
        })))])
    monkeypatch.setattr(ai_service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result = await ai_service.AIService().chat(activity, [], "What percentage of completed customers in 2024 returned in 2025?")
    assert result["metadata"]["status"] == "succeeded"
    assert "33.3%" in result["content"] and "99.9%" not in result["content"]


async def test_chat_null_defaults_and_lowercase_categories_do_not_hide_valid_results(activity, monkeypatch):
    import json

    from app.services import ai_service

    async def create(**kwargs):
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "answer_kind": "calculated", "plan": {"aggregation": "sum", "column": "amount", "order": None, "limit": None,
                "filters": [{"column": "status", "op": "in", "values": ["completed"]}]},
        })))])
    monkeypatch.setattr(ai_service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result = await ai_service.AIService().chat(activity, [], "Total completed amount?")
    assert result["metadata"]["status"] == "succeeded"
    assert result["metadata"]["comparison"]["groups"][0]["value"] == 100


async def test_model_category_case_is_resolved_before_calculation_and_drilldown(activity):
    plan = retention(filters=[{"column": "status", "op": "in", "values": ["completed"]}])
    result = await compare(activity, plan, resolve_categories=True)
    assert result["cohort"] == {"baseline_entities": 3, "returning_entities": 1}
    assert result["plan"]["filters"][0]["values"] == ["Completed"]
    records = await entries(activity, EntryRequest(kind="comparison", comparison=ComparisonPlan(**result["plan"])))
    assert records["matched_entries"] == 4


@pytest.mark.parametrize("value", ["missing", "Completed' OR 1=1 --"])
async def test_nonexistent_model_categories_need_clarification(activity, value):
    with pytest.raises(ComparisonUnavailable, match="does not match a recorded category"):
        await compare(activity, retention(filters=[{"column": "status", "op": "in", "values": [value]}]), resolve_categories=True)


async def test_ambiguous_case_variants_are_not_silently_merged(tmp_path):
    analysis = await make_analysis(tmp_path, pl.DataFrame({"status": ["Completed", "COMPLETED"], "amount": [10., 20.]}))
    plan = ComparisonPlan(aggregation="sum", column="amount", filters=[{"column": "status", "op": "in", "values": ["completed"]}])
    with pytest.raises(ComparisonUnavailable, match="multiple recorded categories"):
        await compare(analysis, plan, resolve_categories=True)
    exact = plan.model_copy(update={"filters": [plan.filters[0].model_copy(update={"values": ["Completed"]})]})
    result = await compare(analysis, exact, resolve_categories=True)
    assert result["groups"][0]["value"] == 10


async def test_async_file_combination_persists_resolution_and_full_profile(tmp_path):
    source_files = []
    for name, frame in [("customers.csv", pl.DataFrame({"customer_id": ["A", "B"], "segment": ["VIP", "Other"]})),
                        ("orders.csv", pl.DataFrame({"customer_id": ["A", "A", "B"], "amount": [10, 20, 30]}))]:
        path = tmp_path / name
        frame.write_csv(path)
        source_files.append(SimpleNamespace(storage_path=str(path), original_filename=name))
    context = {}
    profile = await FileProcessor().combine_uploaded_files(source_files, str(tmp_path / "combined.parquet"), context)
    assert profile["row_count"] == 3
    assert context["relationship_resolution"]["status"] == "enriched"


async def test_truncated_lookup_cannot_claim_full_key_uniqueness(tmp_path):
    sources = []
    for name, frame in [("customers.csv", pl.DataFrame({"customer_id": ["A", "B", "A"], "segment": ["VIP", "Other", "Conflict"]})),
                        ("orders.csv", pl.DataFrame({"customer_id": ["A", "A"], "amount": [10, 20]}))]:
        path = tmp_path / name
        frame.write_csv(path)
        sources.append(SimpleNamespace(storage_path=str(path), original_filename=name))
    processor = FileProcessor()
    processor.SAMPLE_ROWS = 2
    context = {}
    await processor.combine_uploaded_files(sources, str(tmp_path / "combined.parquet"), context)
    assert context["source_sample_truncated"]
    assert context["relationship_resolution"]["status"] == "unresolved"
    assert context["combine_strategy"] == "portfolio"


async def test_related_excel_sheets_use_the_same_transaction_preserving_join(tmp_path):
    from openpyxl import Workbook

    workbook = Workbook()
    donors = workbook.active
    donors.title = "Customers"
    donors.append(["customer_id", "segment"])
    donors.append(["C001", "High Value"])
    donors.append(["C002", "Mid-Level"])
    gifts = workbook.create_sheet("Orders")
    gifts.append(["order_id", "customer_id", "amount"])
    gifts.append(["G001", "C001", 10])
    gifts.append(["G002", "C001", 20])
    gifts.append(["G003", "C002", 30])
    path = tmp_path / "related.xlsx"
    workbook.save(path)
    processor = FileProcessor()
    frame = processor._read_file(str(path), ".xlsx")
    assert frame.height == 3
    assert frame["amount"].sum() == 60
    assert frame["segment"].to_list() == ["High Value", "High Value", "Mid-Level"]
    report = processor._parser_metadata(str(path), ".xlsx")
    assert report["relationship_resolution"]["sheet_names"] == ["Customers", "Orders"]


@pytest.mark.parametrize("references", [0, 1])
async def test_rerun_rebuilds_from_original_owner_scoped_files(tmp_path, monkeypatch, references):
    from app.api.v1.endpoints import analyses

    owner = SimpleNamespace(id=uuid4(), storage_used_bytes=100, subscription_plan="pro")
    originals = []
    for name, frame in [("customers.csv", pl.DataFrame({"customer_id": ["A", "B"], "segment": ["VIP", "Other"]})),
                        ("orders.csv", pl.DataFrame({"customer_id": ["A", "A", "B"], "amount": [10, 20, 30]}))]:
        path = tmp_path / name
        frame.write_csv(path)
        originals.append(SimpleNamespace(id=uuid4(), storage_path=str(path), original_filename=name))
    old_path = tmp_path / "old.parquet"
    pl.DataFrame({"old": [1]}).write_parquet(old_path)
    old_file = SimpleNamespace(id=uuid4(), storage_path=str(old_path), file_size=100)
    analysis = SimpleNamespace(id=uuid4(), name="Combined", file=old_file, metadata_={"upload_context": {
        "combined": True, "combine_strategy": "portfolio", "source_files": [{"id": str(f.id)} for f in originals],
        "cleaning": {"enabled": False, "mode": "raw"},
    }})
    db = AsyncMock()
    db.add = Mock()
    db.execute.side_effect = [Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=originals)))), Mock(scalar_one=Mock(return_value=references))]
    monkeypatch.setattr(analyses.settings, "upload_dir", str(tmp_path / "generated"))
    monkeypatch.setattr(analyses, "ensure_storage_quota", Mock())
    new_file = await analyses._regenerate_cleaned_file_for_rerun(analysis=analysis, current_user=owner, db=db)
    rebuilt = pl.read_parquet(new_file.storage_path)
    assert rebuilt.height == 3 and rebuilt["amount"].sum() == 60
    assert analysis.metadata_["upload_context"]["combine_strategy"] == "relational"
    assert old_path.is_file()  # Physical cleanup waits for the database commit.
    assert analysis._rerun_obsolete_paths == ([str(old_path)] if references == 0 else [])
    assert all(Path(f.storage_path).is_file() for f in originals)
    assert owner.storage_used_bytes == new_file.file_size + (100 if references else 0)
    sql = str(db.execute.call_args_list[0].args[0])
    assert "user_id" in sql
    assert "@>" in str(db.execute.call_args_list[1].args[0])
    if references:
        db.delete.assert_not_awaited()


async def test_rerun_missing_originals_fails_without_claiming_a_repaired_report():
    from fastapi import HTTPException

    from app.api.v1.endpoints import analyses

    old = SimpleNamespace(id=uuid4(), storage_path="old.parquet")
    analysis = SimpleNamespace(file=old, metadata_={"upload_context": {
        "combined": True, "source_files": [{"id": str(uuid4())}, {"id": str(uuid4())}],
    }})
    db = AsyncMock()
    db.add = Mock()
    db.execute.return_value = Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=[]))))
    with pytest.raises(HTTPException, match="original source file") as caught:
        await analyses._regenerate_cleaned_file_for_rerun(analysis=analysis, current_user=SimpleNamespace(id=uuid4()), db=db)
    assert caught.value.status_code == 409
    assert analysis.file is old
    db.add.assert_not_called()
    db.delete.assert_not_awaited()


async def test_repeated_rerun_does_not_replace_an_already_processing_copy(monkeypatch):
    from fastapi import HTTPException

    from app.api.v1.endpoints import analyses

    analysis = SimpleNamespace(status="processing")
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=analysis))
    rebuild = AsyncMock()
    monkeypatch.setattr(analyses, "_regenerate_cleaned_file_for_rerun", rebuild)
    with pytest.raises(HTTPException) as caught:
        await analyses.rerun_analysis.__wrapped__(None, uuid4(), SimpleNamespace(id=uuid4()), db)
    assert caught.value.status_code == 409
    rebuild.assert_not_awaited()


async def test_queue_failure_allows_a_rerun_retry(monkeypatch):
    from app.api.v1.endpoints import analyses

    analysis = SimpleNamespace(id=uuid4(), status="completed", insights=[])
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=analysis))
    monkeypatch.setattr(analyses, "_regenerate_cleaned_file_for_rerun", AsyncMock(return_value=None))
    monkeypatch.setattr(analyses, "_analysis_detail_response", Mock(return_value={}))
    monkeypatch.setattr(analyses.run_analysis_task, "delay", Mock(side_effect=RuntimeError("queue unavailable")))
    await analyses.rerun_analysis.__wrapped__(None, analysis.id, SimpleNamespace(id=uuid4()), db)
    assert analysis.status == "failed"
    assert "queued" in analysis.error_message
