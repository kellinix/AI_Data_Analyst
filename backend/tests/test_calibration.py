from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analytics import calibration
from app.analytics.calibration import confidence_fields, load_calibration_table
from app.analytics.recommendations import generate_recommendations
from app.services.ai_service import _normalize_recommendation

COMMITTED_TABLE = Path(calibration.__file__).with_name("calibration_table.json")


def _write_table(path: Path, sources: dict) -> None:
    path.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    load_calibration_table.cache_clear()


def test_defaults_when_no_table_exists():
    assert confidence_fields("ai:high") == {
        "confidence": 0.85,
        "confidence_source": "ai:high",
        "confidence_method": "default",
    }


def test_measured_value_replaces_default(empty_calibration_table):
    _write_table(empty_calibration_table, {"ai:high": {"confidence": 0.61, "n": 40}})

    assert confidence_fields("ai:high") == {
        "confidence": 0.61,
        "confidence_source": "ai:high",
        "confidence_method": "measured",
    }


@pytest.mark.parametrize(
    "entry",
    [
        {"confidence": 0.61, "n": 9},  # below MIN_SAMPLES
        {"confidence": 1.4, "n": 40},  # not a probability
        {"confidence": "high", "n": 40},
        {"n": 40},
        "0.61",
    ],
)
def test_unusable_entries_fall_back_to_default(empty_calibration_table, entry):
    _write_table(empty_calibration_table, {"ai:high": entry})

    assert confidence_fields("ai:high")["confidence_method"] == "default"
    assert confidence_fields("ai:high")["confidence"] == 0.85


def test_malformed_table_falls_back_to_defaults(empty_calibration_table):
    empty_calibration_table.write_text("{not json", encoding="utf-8")
    load_calibration_table.cache_clear()

    assert confidence_fields("rule:anomaly")["confidence"] == 0.78


def test_forecast_default_is_the_forecasts_own_confidence():
    assert confidence_fields("rule:forecast", default=0.63)["confidence"] == 0.63


def test_ai_recommendations_use_measured_tier_values(empty_calibration_table):
    _write_table(empty_calibration_table, {"ai:medium": {"confidence": 0.42, "n": 25}})

    rec = _normalize_recommendation({"problem": "x", "priority": "Medium"})

    assert rec["confidence"] == 0.42
    assert rec["confidence_source"] == "ai:medium"
    assert rec["confidence_method"] == "measured"


def test_rule_recommendations_are_tagged_with_their_source(empty_calibration_table):
    _write_table(empty_calibration_table, {"rule:anomaly": {"confidence": 0.33, "n": 30}})

    recs = generate_recommendations(
        kpis=[{"column": "revenue", "value": 100000}],
        data_quality={
            "score": 60,
            "issues": [{"type": "missing_values", "severity": "high", "description": "30% missing"}],
        },
        anomalies=[{"column": "revenue", "description": "One record reached 9,999.", "score": 4.2}],
        forecasts=[
            {
                "metric": "revenue",
                "latest_value": 10000,
                "observations": 12,
                "change_percent_next_month": 20.0,
                "confidence": 0.66,
                "predictions": {"next_month": {"value": 12000}},
            }
        ],
    )

    by_source = {rec["confidence_source"]: rec for rec in recs}
    assert set(by_source) == {"rule:data_quality", "rule:forecast", "rule:anomaly"}
    assert by_source["rule:anomaly"]["confidence"] == 0.33
    assert by_source["rule:forecast"]["confidence"] == 0.66
    assert by_source["rule:data_quality"]["confidence"] == 0.9


def test_committed_table_is_valid():
    """The table shipped with the app must parse and contain only usable entries."""
    payload = json.loads(COMMITTED_TABLE.read_text(encoding="utf-8"))

    assert isinstance(payload["sources"], dict)
    for source, entry in payload["sources"].items():
        assert source.startswith(("ai:", "rule:")), source
        assert 0.0 <= entry["confidence"] <= 1.0, source
        assert entry["n"] >= calibration.MIN_SAMPLES, source
