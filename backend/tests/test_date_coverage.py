from __future__ import annotations

from copy import deepcopy
from datetime import date

import duckdb
import pytest

from app.analytics.analysis_evidence import analysis_evidence, date_coverage_limitations
from app.analytics.forecasting import generate_forecasts
from app.analytics.measure_semantics import is_observation_date
from app.services.report_language import VERSION, present_metadata

OLD_WARNING = (
    "The latest recorded date is 18 May 2016. "
    "These figures are too old for a current forward-looking forecast."
)


def date_field(name, original=None):
    return {"name": name, "is_date": True, "analysis_role": "temporal_dimension",
            "measure_grain": {"kind": "lookup", "repeated": True, "source_table": "reference.csv",
                              "source_column": original or name}}


@pytest.mark.parametrize("name", ["Store_Open_Date", "storeopendate", "birth_date", "dob", "due_date", "release_date", "course_start_date"])
def test_lifecycle_dates_cannot_establish_record_recency(name):
    stats = {"schema": [date_field(name)], "date_range": {name: {"min": "1990-01-01", "max": "2016-05-18"}}}
    notes = analysis_evidence(stats, {})["limitations"]
    assert not any("too old" in note or "latest recorded date" in note for note in notes)
    assert any("when these figures were recorded" in note for note in notes)


def test_original_header_provenance_protects_an_opaque_cleaned_date_name():
    stats = {"schema": [date_field("date_related_2", "StoreOpenDate")],
             "date_range": {"date_related_2": {"max": "2016-05-18"}}}
    assert not any("too old" in note for note in date_coverage_limitations(stats))


def test_newer_lifecycle_date_cannot_hide_an_old_transaction_date():
    stats = {"schema": [date_field("order_date"), date_field("due_date")], "date_range": {
        "order_date": {"max": "2023-12-31"}, "due_date": {"max": "2035-01-01"}}}
    notes = date_coverage_limitations(stats)
    assert len(notes) == 1 and "31 Dec 2023" in notes[0] and "too old" in notes[0]


@pytest.mark.parametrize("name", ["transaction_date", "shipdate", "period_date", "snapshot_date", "asof_date"])
def test_valid_old_recording_dates_keep_their_historical_warning(name):
    stats = {"schema": [date_field(name)], "date_range": {name: {"max": "2023-12-31"}}}
    assert any("31 Dec 2023" in note and "too old" in note for note in date_coverage_limitations(stats))


def test_recent_observation_retains_the_existing_freshness_behavior():
    stats = {"schema": [date_field("transaction_date"), date_field("Store_Open_Date")], "date_range": {
        "transaction_date": {"max": date.today().isoformat()}, "Store_Open_Date": {"max": "2016-05-18"}}}
    assert date_coverage_limitations(stats) == []


@pytest.mark.parametrize("current_version", [False, True])
def test_saved_notes_are_corrected_before_repeated_view_shortcut_without_rewriting_summary(current_version):
    unrelated = "The owner checked the physical stock count."
    metadata = {"schema": [date_field("store_open_date", "Store_Open_Date")],
                "date_range": {"store_open_date": {"max": "2016-05-18"}},
                "analysis_evidence": {"limitations": [unrelated, OLD_WARNING]},
                "data_profile": {"analysis_evidence": {"limitations": [unrelated, OLD_WARNING]}}}
    if current_version:
        metadata["presentation_version"] = VERSION
    before = deepcopy(metadata)
    shown, summary = present_metadata(metadata, "Stock report checked by the owner.")
    assert metadata == before and summary == "Stock report checked by the owner."
    for evidence in [shown["analysis_evidence"], shown["data_profile"]["analysis_evidence"]]:
        assert unrelated in evidence["limitations"]
        assert not any("too old" in note for note in evidence["limitations"])
        assert any("when these figures were recorded" in note for note in evidence["limitations"])
    assert present_metadata(shown, summary) == (shown, summary)
    assert shown["date_range"] == metadata["date_range"]


def test_saved_authored_notes_without_generated_date_markers_are_preserved():
    notes = ["The source owner described this extract as current.", "Check the stock against the original file."]
    stats = {"schema": [date_field("Store_Open_Date")], "date_range": {"Store_Open_Date": {"max": "2016-05-18"}}}
    assert date_coverage_limitations(stats, notes) == notes


def test_legacy_transaction_bounds_without_saved_schema_keep_their_warning():
    assert any("too old" in note for note in date_coverage_limitations({"date_range": {"shipdate": {"max": "2023-12-31"}}}))


def test_valid_linked_transaction_dates_keep_forecast_figures_and_lifecycle_dates_do_not_enable_them():
    rows = [(date(2025, month, 1), 1000.0 + month * 50 + (month % 3) * 10) for month in range(1, 13)]
    metric = {"name": "revenue", "is_numeric": True, "analysis_role": "metric"}
    observation = date_field("order_date", "OrderDate")
    opening = date_field("Store_Open_Date")
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE data (order_date DATE, revenue DOUBLE, Store_Open_Date DATE)")
        connection.executemany("INSERT INTO data VALUES (?, ?, DATE '2016-05-18')", rows)
        expected = generate_forecasts(connection, [observation, metric], [{"column": "revenue"}], reference_date=date(2026, 1, 5))
        assert len(expected) == 1
        assert generate_forecasts(connection, [opening, observation, metric], [{"column": "revenue"}], reference_date=date(2026, 1, 5)) == expected
        assert generate_forecasts(connection, [opening, metric], [{"column": "revenue"}], reference_date=date(2026, 1, 5)) == []
    assert not is_observation_date("snapshot_date")
    assert is_observation_date("snapshot_date", include_snapshot=True)
