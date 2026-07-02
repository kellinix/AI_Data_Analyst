from datetime import date, datetime

import polars as pl

from app.services.file_processor import FileProcessor


def test_promotes_excel_header_below_report_title():
    processor = FileProcessor()
    raw = pl.DataFrame(
        {
            "column_1": [
                "Table 1 - Count of CoS Used in 2025 by Organisation",
                "Organisation Name",
                '"K" Line Energy Shipping (UK) Limited',
                "ABB Limited",
            ],
            "column_2": [
                None,
                "Global Business Mobility & Intra Company Transfer",
                "5",
                "18",
            ],
        }
    )

    normalized = processor._normalize_report_table(raw)

    assert normalized.columns == [
        "Organisation Name",
        "Global Business Mobility & Intra Company Transfer",
    ]
    assert normalized.height == 2
    assert normalized["Organisation Name"].to_list() == [
        '"K" Line Energy Shipping (UK) Limited',
        "ABB Limited",
    ]
    assert normalized["Global Business Mobility & Intra Company Transfer"].to_list() == [
        5.0,
        18.0,
    ]


def test_promotes_first_row_when_excel_has_normal_header():
    processor = FileProcessor()
    raw = pl.DataFrame(
        {
            "column_1": ["Customer Name", "Acme Ltd", "Beta Ltd"],
            "column_2": ["Total Revenue", "1200", "3400"],
        }
    )

    normalized = processor._normalize_report_table(raw)

    assert normalized.columns == ["Customer Name", "Total Revenue"]
    assert normalized.height == 2
    assert normalized["Total Revenue"].to_list() == [1200.0, 3400.0]


def test_stacks_same_schema_excel_sheets_with_sheet_name():
    processor = FileProcessor()
    sheets = {
        "Table 1": pl.DataFrame(
            {
                "column_1": ["Organisation Name", "Acme Ltd", "Beta Ltd"],
                "column_2": ["COS Used", "10", "20"],
            }
        ),
        "Table 2": pl.DataFrame(
            {
                "column_1": ["Organisation Name", "Gamma Ltd"],
                "column_2": ["COS Used", "30"],
            }
        ),
    }

    normalized = processor._normalize_excel_sheets(sheets)

    assert normalized.height == 3
    assert normalized.columns == ["Organisation Name", "COS Used", "Sheet"]
    assert normalized["COS Used"].to_list() == [10.0, 20.0, 30.0]
    assert normalized["Sheet"].to_list() == ["Table 1", "Table 1", "Table 2"]


def test_joins_excel_sheets_with_shared_dimension_and_distinct_metrics():
    processor = FileProcessor()
    sheets = {
        "ICT GBM": pl.DataFrame(
            {
                "column_1": ["Organisation Name", "Acme Ltd", "Beta Ltd"],
                "column_2": ["Global Business Mobility & Intra Company Transfer", "10", "20"],
            }
        ),
        "Skilled Worker": pl.DataFrame(
            {
                "column_1": ["Organisation Name", "Acme Ltd", "Gamma Ltd"],
                "column_2": ["Skilled Worker & Tier 2", "30", "40"],
            }
        ),
    }

    normalized = processor._normalize_excel_sheets(sheets)

    assert normalized.columns == [
        "Organisation Name",
        "Global Business Mobility & Intra Company Transfer",
        "Skilled Worker & Tier 2",
    ]
    assert normalized.height == 3

    rows = {
        row["Organisation Name"]: row
        for row in normalized.to_dicts()
    }
    assert rows["Acme Ltd"]["Global Business Mobility & Intra Company Transfer"] == 10.0
    assert rows["Acme Ltd"]["Skilled Worker & Tier 2"] == 30.0
    assert rows["Beta Ltd"]["Global Business Mobility & Intra Company Transfer"] == 20.0
    assert rows["Beta Ltd"]["Skilled Worker & Tier 2"] == 0.0
    assert rows["Gamma Ltd"]["Global Business Mobility & Intra Company Transfer"] == 0.0
    assert rows["Gamma Ltd"]["Skilled Worker & Tier 2"] == 40.0


def test_clean_dataframe_imputes_missing_values_and_drops_rows_without_metrics():
    processor = FileProcessor()
    df = pl.DataFrame(
        {
            "Total Sales": [10.0, None, 30.0, None],
            "Profit": [1.0, 5.0, None, None],
            "Region": ["North", "Unknown", None, "South"],
        }
    )

    cleaned, report = processor.clean_dataframe(
        df,
        {
            "missing_data_strategy": "smart",
            "remove_duplicates": False,
            "semantic_categorical_merging": False,
        },
    )

    assert cleaned.height == 3
    assert cleaned["total_sales"].null_count() == 0
    assert cleaned["profit"].null_count() == 0
    assert cleaned["region"].to_list() == ["North", "Unknown", "Unknown"]
    assert report["dropped_rows_missing_critical_metrics"] == 1
    assert report["missing_values"]["numeric_imputations"]
    assert report["missing_values"]["categorical_imputations"]


def test_clean_dataframe_collapses_messy_text_whitespace():
    processor = FileProcessor()
    df = pl.DataFrame({"Region": ["  North   America  ", "\tEurope\nWest "]})

    cleaned, _ = processor.clean_dataframe(
        df,
        {
            "missing_data_strategy": "none",
            "remove_duplicates": False,
            "semantic_categorical_merging": False,
        },
    )

    assert cleaned["region"].to_list() == ["North America", "Europe West"]


def test_fuzzy_deduplicate_keeps_similar_names_when_metrics_differ():
    processor = FileProcessor()
    df = pl.DataFrame(
        {
            "Customer": ["John Smith", "Jon Smith", "John Smith"],
            "Total Sales": [10.0, 10.0, 20.0],
        }
    )

    cleaned, report = processor.clean_dataframe(
        df,
        {
            "remove_duplicates": False,
            "fuzzy_deduplicate": True,
            "missing_data_strategy": "none",
            "semantic_categorical_merging": False,
        },
    )

    assert cleaned.height == 2
    assert cleaned["total_sales"].to_list() == [10.0, 20.0]
    assert report["removed_fuzzy_duplicate_rows"] == 1


def test_normalize_dates_parses_mixed_date_formats_to_standard_date():
    processor = FileProcessor()
    df = pl.DataFrame(
        {
            "Event Date": ["2025-01-31", "31/01/2025", "02-15-2025", "15 Feb 2025"],
            "Value": [1, 2, 3, 4],
        }
    )

    cleaned, report = processor.clean_dataframe(
        df,
        {
            "normalize_dates": True,
            "missing_data_strategy": "none",
            "remove_duplicates": False,
            "semantic_categorical_merging": False,
        },
    )

    assert cleaned["event_date"].to_list() == [
        date(2025, 1, 31),
        date(2025, 1, 31),
        date(2025, 2, 15),
        date(2025, 2, 15),
    ]
    assert report["date_normalization"]["columns"][0]["standard"] == "YYYY-MM-DD"


def test_date_strings_are_not_converted_to_numbers_before_normalization():
    processor = FileProcessor()
    df = pl.DataFrame(
        {
            "Match Date": ["2026-07-10", "2026-07-11", "2026-07-12"],
            "Expected Goals": ["0.10", "0.20", "0.30"],
        }
    )

    cleaned, report = processor.clean_dataframe(
        df,
        {
            "normalize_dates": True,
            "parse_currency_percent": True,
            "missing_data_strategy": "none",
            "remove_duplicates": False,
            "semantic_categorical_merging": False,
        },
    )

    assert cleaned["match_date"].to_list() == [
        date(2026, 7, 10),
        date(2026, 7, 11),
        date(2026, 7, 12),
    ]
    assert cleaned["expected_goals"].to_list() == [0.1, 0.2, 0.3]
    assert report["converted_date_columns"] == ["match_date"]
    converted_numeric = {item["column"] for item in report["converted_numeric_columns"]}
    assert "match_date" not in converted_numeric
    assert "expected_goals" in converted_numeric


def test_normalize_dates_converts_timezone_timestamps_to_utc():
    processor = FileProcessor()
    df = pl.DataFrame(
        {
            "Created At": [
                "2025-01-01T10:00:00+01:00",
                "2025-01-01 09:00:00Z",
            ],
            "Value": [1, 2],
        }
    )

    cleaned, report = processor.clean_dataframe(
        df,
        {
            "normalize_dates": True,
            "missing_data_strategy": "none",
            "remove_duplicates": False,
            "semantic_categorical_merging": False,
        },
    )

    assert cleaned["created_at"].to_list() == [
        datetime(2025, 1, 1, 9, 0),
        datetime(2025, 1, 1, 9, 0),
    ]
    assert report["date_normalization"]["columns"][0]["standard"] == "UTC datetime"


def test_clean_dataframe_caps_outliers_without_dropping_rows():
    processor = FileProcessor()
    df = pl.DataFrame(
        {
            "Revenue": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 10000.0],
            "Region": ["A"] * 10,
        }
    )

    cleaned, report = processor.clean_dataframe(
        df,
        {
            "outlier_policy": "cap",
            "missing_data_strategy": "none",
            "remove_duplicates": False,
            "semantic_categorical_merging": False,
        },
    )

    assert cleaned.height == 10
    assert cleaned["revenue"].max() < 10000.0
    assert report["capped_outlier_values"] == 1
    assert report["outlier_capping"]["columns"][0]["column"] == "revenue"


def test_clean_dataframe_casts_currency_and_percentage_text_to_numbers():
    processor = FileProcessor()
    df = pl.DataFrame(
        {
            "Price": ["$15.00", "15€", "USD 1.2k", "(£3,000)", "4,500"],
            "Conversion Rate": ["12.5%", "10%", "8.25%", "0%", "100%"],
        }
    )

    cleaned, report = processor.clean_dataframe(
        df,
        {
            "parse_currency_percent": True,
            "missing_data_strategy": "none",
            "remove_duplicates": False,
            "semantic_categorical_merging": False,
        },
    )

    assert cleaned["price"].to_list() == [15.0, 15.0, 1200.0, -3000.0, 4500.0]
    assert cleaned["conversion_rate"].to_list() == [12.5, 10.0, 8.25, 0.0, 100.0]
    converted = {item["column"]: item for item in report["converted_numeric_columns"]}
    assert converted["price"]["detected_currency"] is True
    assert converted["conversion_rate"]["detected_percent"] is True
