"""Label derivation, checked against the real column names it was built for.

These are the actual headers from the six Government Major Projects Portfolio
workbooks, which is where the problem was found: a chart title read
"Financial Year Baseline Currency M Including Non Government Costs by
Department", and one column's "label" was its whole 200-character definition.
"""

from __future__ import annotations

import pytest

from app.analytics.labels import derive_label

GMPP_COLUMNS = [
    (
        "financial_year_baseline_currency_m_including_non_government_costs",
        "Financial Year Baseline (M)",
    ),
    (
        "financial_year_forecast_currency_m_including_non_government_costs",
        "Financial Year Forecast (M)",
    ),
    (
        "total_baseline_whole_life_costs_currency_m_including_non_government_costs",
        "Total Baseline Whole Life Costs (M)",
    ),
    ("total_baseline_benefits_currency_m", "Total Baseline Benefits (M)"),
    ("financial_year_variance_pct", "Financial Year Variance %"),
    ("gmpp_id_number", "GMPP ID Number"),
    ("department", "Department"),
    ("annual_report_category", "Annual Report Category"),
    ("project_name", "Project Name"),
    ("source_file", "Source File"),
]


@pytest.mark.parametrize(("column", "expected"), GMPP_COLUMNS)
def test_real_portfolio_columns_get_readable_labels(column, expected):
    assert derive_label(column) == expected


def test_a_name_that_restates_itself_is_cut_at_the_repeat():
    """The delivery-confidence column's name contains its own definition, so
    humanising it produced a 200-character chart title."""
    column = (
        "ipa_delivery_confidence_assessment_a_delivery_confidence_assessment_of_the_"
        "project_at_a_fixed_point_in_time_using_a_three_point_scale_red_amber_green_"
        "definitions_in_the_ipa_annual_report_on_major_projects"
    )

    assert derive_label(column) == "IPA Delivery Confidence Assessment"


def test_labels_stay_short_enough_for_a_chart_title():
    """Two of these are concatenated into "X by Y", so each must leave room."""
    for column, _ in GMPP_COLUMNS:
        assert len(derive_label(column)) <= 40


def test_ordinary_short_names_are_left_alone():
    assert derive_label("revenue") == "Revenue"
    assert derive_label("customer_id") == "Customer ID"
    assert derive_label("q1_sales") == "Q1 Sales"


def test_a_name_with_nothing_usable_does_not_crash():
    assert derive_label("") == ""
    assert derive_label("___") == ""
