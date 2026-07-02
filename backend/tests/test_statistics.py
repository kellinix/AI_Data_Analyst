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
