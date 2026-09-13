import duckdb

from app.analytics.data_quality import analyze_data_quality

_SKEW_SCHEMA =[{"name": "cost", "is_numeric": True, "is_date": False, "analysis_role": "metric"}]
# Quartiles are read from the stats, not recomputed: q1=20, q3=40 puts the IQR
# fence at -10 and 70.
_SKEW_STATS = {"cost": {"p25": 20.0, "p75": 40.0, "min": 10.0}}


def _costs(values: list[float]) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE data (cost DOUBLE)")
    conn.executemany("INSERT INTO data VALUES (?)", [(value,) for value in values])
    return conn


def test_a_right_skewed_metric_is_not_reported_as_a_defect():
    """Regression: a portfolio containing HS2 always has values far above the
    IQR fence. Reporting that as a medium-severity quality issue told a
    non-technical reader their data was faulty and docked their score, and
    quoted a "typical range" starting at -300 for a column of costs."""
    conn = _costs([float(v) for v in range(10, 50)] + [4000.0, 5000.0])

    quality = analyze_data_quality(conn, _SKEW_SCHEMA, _SKEW_STATS, "data")

    issue = next(i for i in quality["issues"] if i["column"] == "cost")
    assert issue["type"] == "wide_spread"
    assert issue["severity"] == "low"
    # The quoted range is clamped to a value the column can actually reach.
    assert "most are between 10 and 70" in issue["description"]


def test_values_below_a_reachable_floor_are_still_flagged():
    """Skew is the subject matter; a cost of -500 is not."""
    conn = _costs([float(v) for v in range(10, 50)] + [-500.0])

    quality = analyze_data_quality(
        conn, _SKEW_SCHEMA, {"cost": {"p25": 20.0, "p75": 40.0, "min": -500.0}}, "data"
    )

    issue = next(i for i in quality["issues"] if i["column"] == "cost")
    assert issue["type"] == "outliers"
    assert issue["severity"] == "medium"


def test_duplicate_count_groups_by_actual_columns():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE data AS
        SELECT * FROM (
            VALUES
                ('Acme Ltd', 10),
                ('Beta Ltd', 20),
                ('Gamma Ltd', 30)
        ) AS t(organisation, value)
        """
    )
    schema = [
        {"name": "organisation", "is_numeric": False, "is_date": False},
        {"name": "value", "is_numeric": True, "is_date": False},
    ]

    quality = analyze_data_quality(conn, schema, {"value": {}}, "data")

    assert not any(issue["type"] == "duplicates" for issue in quality["issues"])


def test_mostly_duplicated_dataset_is_critical_and_scores_low():
    """A dataset where most rows are exact copies must not score in the
    'healthy' band — regression test for 96/100 on a 70%-duplicate file."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE data (organisation VARCHAR, value INTEGER)")
    conn.executemany(
        "INSERT INTO data VALUES (?, ?)",
        [("Acme Ltd", 10)] * 8 + [("Beta Ltd", 20), ("Gamma Ltd", 30)],
    )
    schema = [
        {"name": "organisation", "is_numeric": False, "is_date": False},
        {"name": "value", "is_numeric": True, "is_date": False},
    ]

    quality = analyze_data_quality(conn, schema, {"value": {}}, "data")

    duplicate_issue = next(i for i in quality["issues"] if i["type"] == "duplicates")
    assert duplicate_issue["severity"] == "critical"
    assert "70%" in duplicate_issue["description"]
    assert quality["score"] <= 85


def test_duplicate_count_reports_exact_duplicate_rows():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE data AS
        SELECT * FROM (
            VALUES
                ('Acme Ltd', 10),
                ('Acme Ltd', 10),
                ('Beta Ltd', 20)
        ) AS t(organisation, value)
        """
    )
    schema = [
        {"name": "organisation", "is_numeric": False, "is_date": False},
        {"name": "value", "is_numeric": True, "is_date": False},
    ]

    quality = analyze_data_quality(conn, schema, {"value": {}}, "data")

    duplicate_issues = [
        issue for issue in quality["issues"] if issue["type"] == "duplicates"
    ]
    assert duplicate_issues[0]["affected_rows"] == 1
