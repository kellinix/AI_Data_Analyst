"""Offline tests for the calibration benchmark: metrics, generator, labels, and
one end-to-end dataset through the real pipeline (AI stubbed, no network)."""

from __future__ import annotations

import csv
import math

import numpy as np
import pytest

from evals.calibration.benchmark import draw_scenarios, write_dataset
from evals.calibration.labels import (
    Label,
    _forecast_title,
    label_rule_recommendation,
    parse_judge_payload,
)
from evals.calibration.metrics import (
    Scored,
    brier_score,
    expected_calibration_error,
    leave_one_dataset_out_brier,
    reliability_table,
    smoothed_rate,
    summarize_by_source,
    wilson_interval,
)

# ── Metrics ────────────────────────────────────────────────────────────────


def _items(pairs, source="s"):
    return [Scored(f"d{i}", source, c, y) for i, (c, y) in enumerate(pairs)]


def test_brier_score():
    assert brier_score(_items([(0.8, True), (0.8, False)])) == pytest.approx((0.04 + 0.64) / 2)
    assert brier_score([]) is None


def test_perfectly_calibrated_bins_have_zero_ece():
    items = _items([(0.5, True), (0.5, False), (0.9, True)] + [(0.9, True)] * 8 + [(0.9, False)])
    table = {row["bin"]: row for row in reliability_table(items)}

    assert table["0.4-0.6"]["hit_rate"] == 0.5
    assert table["0.8-1.0"]["hit_rate"] == pytest.approx(0.9)
    assert expected_calibration_error(items) == pytest.approx(0.0)


def test_overconfidence_shows_up_in_ece():
    items = _items([(0.9, True), (0.9, False), (0.9, False), (0.9, False)])

    assert expected_calibration_error(items) == pytest.approx(0.65)


def test_wilson_interval_and_smoothing():
    low, high = wilson_interval(8, 10)
    assert 0.49 < low < 0.5 and 0.94 < high < 0.95
    assert wilson_interval(0, 0) == (0.0, 1.0)
    assert smoothed_rate(0, 0) == 0.5
    assert smoothed_rate(9, 10) == pytest.approx(10 / 12)


def test_leave_one_dataset_out_never_uses_the_scored_dataset():
    # Two datasets that disagree completely: each is predicted from the other.
    items = [Scored("a", "s", 0.5, True), Scored("b", "s", 0.5, False)]

    # For "a": estimate from "b" = (0+1)/(1+2) = 1/3 -> error (1/3 - 1)^2
    # For "b": estimate from "a" = (1+1)/(1+2) = 2/3 -> error (2/3 - 0)^2
    assert leave_one_dataset_out_brier(items) == pytest.approx(((2 / 3) ** 2 + (2 / 3) ** 2) / 2)


def test_summarize_by_source():
    items = _items([(0.85, True), (0.85, False)], "ai:high") + _items([(0.78, True)], "rule:anomaly")

    summary = summarize_by_source(items)

    assert summary["ai:high"]["n"] == 2
    assert summary["ai:high"]["hit_rate"] == 0.5
    assert summary["ai:high"]["recalibrated_confidence"] == 0.5
    assert summary["rule:anomaly"]["hits"] == 1


# ── Generator ──────────────────────────────────────────────────────────────


def test_scenarios_are_reproducible_and_balanced():
    first, second = draw_scenarios(24), draw_scenarios(24)

    assert [s.describe() for s in first] == [s.describe() for s in second]
    assert sum(s.plant_anomaly for s in first) == 12
    assert sum(s.tracking_outage for s in first) == 8
    assert {s.grain for s in first} == {"weekly", "monthly"}


def test_same_scenario_writes_identical_files(tmp_path):
    scenario = draw_scenarios(4)[1]

    path_a, truth_a = write_dataset(scenario, tmp_path / "a")
    path_b, truth_b = write_dataset(scenario, tmp_path / "b")

    assert path_a.read_bytes() == path_b.read_bytes()
    assert truth_a == truth_b


def _read(path):
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_planted_anomaly_is_the_most_extreme_revenue_record(tmp_path):
    scenario = next(s for s in draw_scenarios(12) if s.plant_anomaly)
    path, truth = write_dataset(scenario, tmp_path)
    rows = _read(path)
    revenue = np.array([float(row[scenario.domain.revenue]) for row in rows])
    z = np.abs(revenue - revenue.mean()) / revenue.std(ddof=1)

    planted = truth["planted_anomaly"]
    assert int(np.argmax(z)) == planted["row_index"]
    assert z[planted["row_index"]] >= 3.5
    assert rows[planted["row_index"]][truth["date_column"]] == planted["date"]


def test_gaps_survive_cleanings_sparse_threshold(tmp_path):
    """Both gap types must exceed the 70% null ratio above which cleaning keeps
    nulls, so the pipeline sees them."""
    scenario = next(s for s in draw_scenarios(24) if s.tracking_outage and s.optional_sparse)
    path, truth = write_dataset(scenario, tmp_path)
    rows = _read(path)

    for column in truth["defect_columns"] + truth["by_design_sparse_columns"]:
        null_ratio = sum(row[column] == "" for row in rows) / len(rows)
        assert null_ratio > 0.7, column
        # The judge relies on this to identify a gap the recommendation doesn't name.
        assert truth["missing_percent_by_column"][column] == round(100 * null_ratio, 1)


def test_holdout_month_is_not_in_the_observed_file(tmp_path):
    scenario = draw_scenarios(4)[0]
    path, truth = write_dataset(scenario, tmp_path)
    months = {row[truth["date_column"]][:7] for row in _read(path)}

    assert truth["holdout"]["month"] not in months
    assert truth["observed_period"][1] == max(months)
    assert all(value is not None for value in truth["holdout"]["totals"].values() if value is not None)


# ── Labels ─────────────────────────────────────────────────────────────────


def _forecast(metric="revenue", change=12.0, latest=1000.0):
    return {"metric": metric, "change_percent_next_month": change, "latest_value": latest}


def _truth(**overrides):
    truth = {
        "date_column": "week_start_date",
        "planted_anomaly": None,
        "defect_columns": [],
        "by_design_sparse_columns": [],
        "holdout": {"totals": {"revenue": 1100.0}},
    }
    truth.update(overrides)
    return truth


@pytest.mark.parametrize(
    ("actual", "expected"),
    [(1100.0, True), (1030.0, False), (900.0, False)],
)
def test_forecast_label_requires_a_material_move_in_the_predicted_direction(actual, expected):
    forecast = _forecast()
    rec = {"confidence_source": "rule:forecast", "title": _forecast_title(forecast)}
    truth = _truth(holdout={"totals": {"revenue": actual}})

    label = label_rule_recommendation(rec, truth=truth, computed={"forecasts": [forecast]})

    assert label.correct is expected


def test_forecast_on_a_broken_metric_is_not_scored():
    forecast = _forecast(metric="new_customers")
    rec = {"confidence_source": "rule:forecast", "title": _forecast_title(forecast)}
    truth = _truth(defect_columns=["new_customers"])

    label = label_rule_recommendation(rec, truth=truth, computed={"forecasts": [forecast]})

    assert label.correct is None


@pytest.mark.parametrize(
    ("column", "expected"),
    [("new_customers", True), ("promo_discount", False), ("revenue", False)],
)
def test_data_quality_label_distinguishes_defects_from_blank_by_design(column, expected):
    rec = {"confidence_source": "rule:data_quality", "problem": "x", "data": {"column": column}}
    truth = _truth(defect_columns=["new_customers"], by_design_sparse_columns=["promo_discount"])

    assert label_rule_recommendation(rec, truth=truth, computed={}).correct is expected


def test_data_quality_label_falls_back_to_matching_the_issue_text():
    issue = {"type": "missing_values", "column": "new_customers", "description": "78.2% of values are missing"}
    rec = {"confidence_source": "rule:data_quality", "problem": "New Customers: 78.2% of values are missing"}
    truth = _truth(defect_columns=["new_customers"])
    computed = {"statistics": {"data_quality": {"issues": [issue]}}}

    assert label_rule_recommendation(rec, truth=truth, computed=computed).correct is True


def _anomaly_rec(anomaly):
    return {"confidence_source": "rule:anomaly", "evidence": anomaly["description"]}


def test_anomaly_label_matches_the_planted_record():
    planted = {
        "date": "2025-03-03",
        "month": "2025-03",
        "dimensions": {"region": "Europe"},
        "columns": ["revenue", "units_sold"],
    }
    hit = {
        "type": "statistical_outlier",
        "column": "units_sold",
        "description": "hit",
        "context": {"week_start_date": "2025-03-03", "region": "Europe"},
    }
    miss = {**hit, "description": "miss", "context": {"week_start_date": "2025-06-02", "region": "Europe"}}
    truth = _truth(planted_anomaly=planted)

    assert label_rule_recommendation(_anomaly_rec(hit), truth=truth, computed={"anomalies": [hit]}).correct
    assert (
        label_rule_recommendation(_anomaly_rec(miss), truth=truth, computed={"anomalies": [miss]}).correct
        is False
    )


def test_any_anomaly_without_a_planted_one_is_wrong():
    anomaly = {"type": "statistical_outlier", "column": "revenue", "description": "x", "context": {}}

    label = label_rule_recommendation(_anomaly_rec(anomaly), truth=_truth(), computed={"anomalies": [anomaly]})

    assert label.correct is False


def test_tracking_recommendations_are_not_scored():
    label = label_rule_recommendation({"confidence_source": "rule:tracking"}, truth=_truth(), computed={})

    assert label.correct is None


@pytest.mark.parametrize(
    ("payload", "correct", "finding"),
    [
        ({"verdict": "SUPPORTED", "planted_finding": "anomaly", "reason": "r"}, True, "anomaly"),
        ({"verdict": "not_supported", "reason": "r"}, False, "none"),
        ({"verdict": "UNVERIFIABLE", "reason": "r"}, None, "none"),
        ({"verdict": "SUPPORTED", "planted_finding": "bogus"}, True, "none"),
    ],
)
def test_parse_judge_payload(payload, correct, finding):
    label = parse_judge_payload(payload)

    assert isinstance(label, Label)
    assert label.correct is correct
    assert label.planted_finding == finding


def test_parse_judge_payload_rejects_unknown_verdicts():
    with pytest.raises(ValueError):
        parse_judge_payload({"verdict": "MAYBE"})


# ── End to end, offline ────────────────────────────────────────────────────


async def test_one_dataset_runs_through_the_production_pipeline(tmp_path, monkeypatch):
    from app.core.config import settings
    from evals.calibration.run_eval import _OfflineAIService, run_dataset, summarize

    monkeypatch.setattr(settings, "semantic_wrangling_enabled", False)
    scenario = next(s for s in draw_scenarios(8) if s.plant_anomaly and s.grain == "weekly")

    result = await run_dataset(scenario, tmp_path, ai_service=_OfflineAIService())

    assert result["recommendations"], "the rule engine should produce recommendations"
    for record in result["recommendations"]:
        assert record["source"].startswith("rule:")
        assert record["label"]["method"] == "rule"
        assert record["label"]["correct"] is not None or record["label"]["reason"]
    assert result["forecasts"], "cleaned weekly data should yield forecasts"

    summary = summarize([result], {"generated_at": "t", "benchmark_version": "v"})
    assert summary["datasets"] == 1
    assert math.isfinite(summary["overall"]["brier_shown"] or 0.0)
