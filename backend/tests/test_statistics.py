from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from app.analytics.statistics import StatisticsEngine


@pytest.fixture
def conn():
    conn = duckdb.connect(":memory:")
    df = pd.DataFrame({
        "revenue": [100.0, 200.0, 300.0, None],
        "category": ["A", "B", "A", "C"],
        "date": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"],
    })
    conn.register("data", df)
    yield conn
    conn.close()


def test_percentage_average_is_weighted_by_the_money_it_applies_to():
    """One project at 100% variance on £1m and one at 0% on £99m average to 50%
    unweighted, which describes neither the portfolio nor anything in it."""
    weighted_conn = duckdb.connect(":memory:")
    weighted_conn.register(
        "data",
        pd.DataFrame({"variance_pct": [100.0, 0.0], "whole_life_cost": [1.0, 99.0]}),
    )

    stats = StatisticsEngine(weighted_conn).describe_all()["numeric_stats"]["variance_pct"]

    assert stats["mean"] == pytest.approx(50.0)
    assert stats["weighted_mean"] == pytest.approx(1.0)
    assert stats["weight_column"] == "whole_life_cost"
    weighted_conn.close()


def test_a_percentage_is_weighted_by_money_from_its_own_family():
    """A financial-year variance is weighted by financial-year money, not by
    whole-life cost — which is far larger but measures something else. The
    biggest money column is not automatically the right one."""
    related_conn = duckdb.connect(":memory:")
    related_conn.register(
        "data",
        pd.DataFrame({
            "financial_year_variance_pct": [100.0, 0.0],
            "financial_year_baseline_cost": [1.0, 99.0],
            "total_whole_life_cost": [5000.0, 5000.0],
        }),
    )

    stats = StatisticsEngine(related_conn).describe_all()["numeric_stats"]
    variance = stats["financial_year_variance_pct"]

    assert variance["weight_column"] == "financial_year_baseline_cost"
    assert variance["weighted_mean"] == pytest.approx(1.0)
    related_conn.close()


def test_describe_all_structure(conn):
    engine = StatisticsEngine(conn)
    result = engine.describe_all()
    assert "schema" in result
    assert "row_count" in result
    assert "numeric_stats" in result
    assert "categorical_stats" in result
    assert "data_quality" in result


def test_numeric_stats(conn):
    engine = StatisticsEngine(conn)
    result = engine.describe_all()
    assert "revenue" in result["numeric_stats"]
    stats = result["numeric_stats"]["revenue"]
    assert stats["mean"] == pytest.approx(200.0, rel=0.01)


def test_categorical_stats(conn):
    engine = StatisticsEngine(conn)
    result = engine.describe_all()
    assert "category" in result["categorical_stats"]
    cat_stats = result["categorical_stats"]["category"]
    assert cat_stats["unique_count"] == 3


def test_data_quality_score(conn):
    engine = StatisticsEngine(conn)
    result = engine.describe_all()
    assert 0 <= result["data_quality"]["score"] <= 100
