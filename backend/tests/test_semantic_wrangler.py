from __future__ import annotations

import polars as pl
import pytest

from app.core.config import settings
from app.services.semantic_wrangler import (
    SemanticWrangler,
    _friendly_chart_title,
    apply_display_metadata_to_charts,
    apply_display_metadata_to_statistics,
)


@pytest.mark.asyncio
async def test_semantic_wrangler_merges_common_category_aliases(monkeypatch) -> None:
    monkeypatch.setattr(settings, "semantic_wrangling_use_embeddings", False)
    monkeypatch.setattr(settings, "semantic_wrangling_enabled", True)

    df = pl.DataFrame(
        {
            "country": ["USA", "United States", "U.S.A.", "us", "Canada"],
            "revenue": [10, 20, 30, 40, 50],
        }
    )

    result = await SemanticWrangler().canonicalize_categorical_values(df)

    assert result.dataframe["country"].to_list() == [
        "United States",
        "United States",
        "United States",
        "United States",
        "Canada",
    ]
    assert result.report["changed_columns"] == ["country"]


@pytest.mark.asyncio
async def test_semantic_wrangler_merges_city_aliases(monkeypatch) -> None:
    monkeypatch.setattr(settings, "semantic_wrangling_use_embeddings", False)
    monkeypatch.setattr(settings, "semantic_wrangling_enabled", True)

    df = pl.DataFrame(
        {
            "city": ["NY", "N.Y.", "New York City", "new york", "Boston"],
            "orders": [1, 2, 3, 4, 5],
        }
    )

    result = await SemanticWrangler().canonicalize_categorical_values(df)

    assert result.dataframe["city"].to_list() == [
        "New York",
        "New York",
        "New York",
        "New York",
        "Boston",
    ]


def test_semantic_display_metadata_adds_friendly_column_and_chart_labels() -> None:
    statistics = {
        "schema": [
            {
                "name": "cust_tx_cnt_q1",
                "dtype": "INTEGER",
                "is_numeric": True,
                "is_date": False,
            }
        ]
    }
    display = {
        "columns": [
            {
                "name": "cust_tx_cnt_q1",
                "label": "Customer Transaction Count (Q1)",
                "description": "Number of customer transactions in Q1.",
            }
        ],
        "charts": [
            {
                "id": "abc123",
                "title": "Customer Transactions in Q1",
                "description": "Q1 transaction volume.",
            }
        ],
    }
    charts = [
        {
            "id": "abc123",
            "type": "histogram",
            "title": "cust_tx_cnt_q1 distribution",
            "description": None,
            "xAxis": "cust_tx_cnt_q1",
            "yAxis": "count",
            "series": ["cust_tx_cnt_q1"],
            "echarts_option": {
                "xAxis": {"type": "category", "name": "cust_tx_cnt_q1"},
                "yAxis": {"type": "value", "name": "Count"},
                "series": [{"type": "bar", "name": "cust_tx_cnt_q1"}],
            },
        }
    ]

    updated_stats = apply_display_metadata_to_statistics(statistics, display)
    updated_charts = apply_display_metadata_to_charts(charts, display)

    assert updated_stats["schema"][0]["display_label"] == "Customer Transaction Count (Q1)"
    assert updated_charts[0]["title"] == "Customer Transactions in Q1"
    assert updated_charts[0]["echarts_option"]["xAxis"]["name"] == "Customer Transaction Count (Q1)"


STACKED_LABELS = {
    "department": "Department",
    "whole_life_cost": "Whole Life Cost",
    "delivery_confidence": "Delivery Confidence",
}


def stacked_title_chart() -> dict:
    """A stacked bar reverses the plain bar's axes: category on x, measure on y."""
    return {
        "type": "bar",
        "xAxis": "department",
        "yAxis": "whole_life_cost",
        "series_by": "delivery_confidence",
        "aggregation": "sum",
    }


def test_stacked_chart_title_names_the_split_dimension():
    """Without this the stacked chart read "Department by Whole Life Cost" —
    backwards, and indistinguishable from the plain bar beside it."""
    summed = stacked_title_chart()
    assert _friendly_chart_title(summed, STACKED_LABELS) == (
        "Whole Life Cost by Department and Delivery Confidence"
    )

    averaged = {**summed, "aggregation": "average"}
    assert _friendly_chart_title(averaged, STACKED_LABELS) == (
        "Avg Whole Life Cost by Department and Delivery Confidence"
    )


def test_a_paragraph_long_column_name_is_trimmed_in_the_title():
    """Regression: the GMPP delivery-confidence column is named with its whole
    definition — 200 characters — giving a stacked-chart title several times
    wider than the chart itself."""
    long_name = (
        "ipa_delivery_confidence_assessment_a_delivery_confidence_assessment_of_the_"
        "project_at_a_fixed_point_in_time_using_a_three_point_scale_red_amber_green_"
        "definitions_in_the_ipa_annual_report_on_major_projects"
    )
    chart = {**stacked_title_chart(), "series_by": long_name}

    title = _friendly_chart_title(chart, STACKED_LABELS)

    assert title.startswith("Whole Life Cost by Department and ")
    assert title.endswith("…")
    # Has to fit one line of a chart card, not merely be shorter than before.
    assert len(title) < 80


def test_friendly_bar_title_keeps_aggregation_distinct():
    """Regression test: a chart's aggregation must survive title regeneration
    (e.g. after chart-data population strips echarts_option._columns) so an
    averaged bar chart is never relabeled as if it were a sum, and an
    outcome-rate chart reads as a rate, not a raw value."""
    labels = {"chol": "Chol", "cp": "Cp", "target": "Target"}

    averaged = {"type": "bar", "xAxis": "chol", "yAxis": "cp", "aggregation": "average"}
    assert _friendly_chart_title(averaged, labels) == "Avg Chol by Cp"

    summed = {"type": "bar", "xAxis": "chol", "yAxis": "cp", "aggregation": "sum"}
    assert _friendly_chart_title(summed, labels) == "Chol by Cp"

    rate = {"type": "bar", "xAxis": "target", "yAxis": "cp", "aggregation": "percent_rate"}
    assert _friendly_chart_title(rate, labels) == "Target Rate by Cp"


def test_bar_chart_titles_survive_full_display_metadata_round_trip():
    """End-to-end version of the aggregation-title regression: a chart built
    by chart_selector, put through chart-data population (which strips
    echarts_option._columns), then through apply_display_metadata_to_charts
    in fallback mode, must still read as an average, not a bare sum."""
    from app.analytics.chart_selector import _horizontal_bar_chart, _outcome_rate_bar_chart
    from app.services.semantic_wrangler import _fallback_display_metadata

    bar = _horizontal_bar_chart("cp", "chol", top_values=[{"value": "0", "count": 5}, {"value": "1", "count": 3}])
    rate = _outcome_rate_bar_chart("cp", "target")

    # Simulate _populate_chart_data's cleanup step.
    for chart in (bar, rate):
        chart["echarts_option"].pop("_columns", None)

    statistics = {"schema": [], "numeric_stats": {}, "categorical_stats": {}}
    display = _fallback_display_metadata(statistics, [bar, rate])
    updated = apply_display_metadata_to_charts([bar, rate], display)

    updated_bar = next(c for c in updated if c["id"] == bar["id"])
    updated_rate = next(c for c in updated if c["id"] == rate["id"])
    assert updated_bar["title"] == "Avg Chol by Cp"
    assert updated_rate["title"] == "Target Rate by Cp"
