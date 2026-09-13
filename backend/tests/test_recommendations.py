from __future__ import annotations

from app.analytics.recommendations import generate_recommendations

LONG_CONTEXT_KEY = (
    "ipa_delivery_confidence_assessment_a_delivery_confidence_assessment_of_the_"
    "project_at_a_fixed_point_in_time_using_a_three_point_scale_red_amber_green"
)


def test_anomaly_recommendation_shortens_a_paragraph_long_context_label():
    """Regression: the anomaly's own description was shortened, but this card
    builds its context string separately, so the recommendation still carried
    200 characters of column name before reaching the value a reader wanted."""
    recs = generate_recommendations(
        kpis=[],
        data_quality={"score": 95, "issues": []},
        anomalies=[
            {
                "column": "financial_year_variance_pct",
                "description": "One record reached 733.00 for Financial Year Variance %.",
                "context": {LONG_CONTEXT_KEY: "Unknown", "department": "DFT"},
            }
        ],
        forecasts=[],
    )

    card = next(r for r in recs if r["title"].startswith("Look into the unusual"))
    assert "…" in card["description"]
    assert "Of The Project At A Fixed Point" not in card["description"]
    # The value, and the dimension that actually explains the record, survive.
    assert "Unknown" in card["description"]
    assert "Department DFT" in card["description"]


def test_quality_issue_creates_specific_recommendation():
    recs = generate_recommendations(
        kpis=[],
        data_quality={
            "score": 72,
            "issues": [
                {
                    "type": "missing_values",
                    "severity": "high",
                    "description": "35.0% of values are missing",
                }
            ],
        },
        anomalies=[],
        forecasts=[],
    )
    assert recs
    assert recs[0]["importance"] == "high"
    assert "35.0%" in recs[0]["problem"]


def test_quality_recommendation_names_the_affected_column():
    """Regression: "78.2% of values are missing" alone didn't say which field,
    for users reading the card or for the calibration benchmark's judge."""
    recs = generate_recommendations(
        kpis=[],
        data_quality={
            "score": 60,
            "issues": [
                {
                    "type": "missing_values",
                    "column": "new_customers",
                    "severity": "critical",
                    "description": "78.2% of values are missing",
                }
            ],
        },
        anomalies=[],
        forecasts=[],
    )

    assert recs[0]["problem"] == "New Customers: 78.2% of values are missing"
    assert recs[0]["data"]["evidence"] == recs[0]["problem"]
    assert recs[0]["data"]["column"] == "new_customers"


def test_forecast_recommendation_uses_metric_evidence():
    recs = generate_recommendations(
        kpis=[{"column": "revenue", "value": 100000}],
        data_quality={"score": 100, "issues": []},
        anomalies=[],
        forecasts=[
            {
                "metric": "revenue",
                "latest_value": 10000,
                "observations": 12,
                "change_percent_next_month": -12.5,
                "confidence": 0.8,
                "predictions": {"next_month": {"value": 8750}},
            }
        ],
    )
    assert recs
    assert recs[0]["financial_opportunity"] == 3000
    assert "revenue" in recs[0]["title"].lower()


def test_anomaly_recommendation_uses_domain_neutral_language():
    recs = generate_recommendations(
        kpis=[],
        data_quality={"score": 100, "issues": []},
        anomalies=[
            {
                "column": "response_time_hours",
                "description": "The highest response time is 42.3 hours.",
                "score": 4.5,
            }
        ],
        forecasts=[],
    )

    assert recs
    assert "organisations" not in recs[0]["title"].lower()
    assert "organisations" not in recs[0]["description"].lower()
    assert "correction" not in recs[0]["description"].lower()
    # This asserted the title contained "standout" — analyst vocabulary that
    # the plain-language pass removed. The intent was domain-neutral wording,
    # so pin that instead: it names the measure in ordinary words.
    assert recs[0]["title"] == "Look into the unusual Response Time Hours"
    assert "outlier" not in recs[0]["title"].lower()
    assert "anomaly" not in recs[0]["title"].lower()
    assert recs[0]["data"]["owner"] == "Operations"
