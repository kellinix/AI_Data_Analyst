from __future__ import annotations

from app.analytics.recommendations import generate_recommendations


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
                "column": "expected_goals_xg",
                "description": "The highest expected goals xG value is 2.31.",
                "score": 4.5,
            }
        ],
        forecasts=[],
    )

    assert recs
    assert "organisations" not in recs[0]["title"].lower()
    assert "organisations" not in recs[0]["description"].lower()
    assert "correction" not in recs[0]["description"].lower()
    assert "standout" in recs[0]["title"].lower()
    assert recs[0]["data"]["owner"] == "Performance Team"
