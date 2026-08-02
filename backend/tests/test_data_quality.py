import duckdb

from app.analytics.data_quality import analyze_data_quality


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
