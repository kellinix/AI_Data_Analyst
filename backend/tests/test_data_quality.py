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
