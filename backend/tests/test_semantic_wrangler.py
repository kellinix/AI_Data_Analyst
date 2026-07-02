from __future__ import annotations

import polars as pl
import pytest

from app.core.config import settings
from app.services.semantic_wrangler import (
    SemanticWrangler,
    apply_display_metadata_to_charts,
    apply_display_metadata_to_statistics,
)


@pytest.mark.asyncio
async def test_semantic_wrangler_merges_common_category_aliases(monkeypatch) -> None:
    monkeypatch.setattr(settings, "semantic_wrangling_use_embeddings", False)
    monkeypatch.setattr(settings, "semantic_wrangling_enabled", True)

    df = pl.DataFrame(
        {
            "country": ["USA", "United States", "U.S.A.", "us", "Canada"],
            "revenue": [10, 20, 30, 40, 50],
        }
    )

    result = await SemanticWrangler().canonicalize_categorical_values(df)

    assert result.dataframe["country"].to_list() == [
        "United States",
        "United States",
        "United States",
        "United States",
        "Canada",
    ]
    assert result.report["changed_columns"] == ["country"]


@pytest.mark.asyncio
async def test_semantic_wrangler_merges_city_aliases(monkeypatch) -> None:
    monkeypatch.setattr(settings, "semantic_wrangling_use_embeddings", False)
    monkeypatch.setattr(settings, "semantic_wrangling_enabled", True)

    df = pl.DataFrame(
        {
            "city": ["NY", "N.Y.", "New York City", "new york", "Boston"],
            "orders": [1, 2, 3, 4, 5],
        }
    )

    result = await SemanticWrangler().canonicalize_categorical_values(df)

    assert result.dataframe["city"].to_list() == [
        "New York",
        "New York",
        "New York",
        "New York",
        "Boston",
    ]


def test_semantic_display_metadata_adds_friendly_column_and_chart_labels() -> None:
    statistics = {
        "schema": [
            {
                "name": "cust_tx_cnt_q1",
                "dtype": "INTEGER",
                "is_numeric": True,
                "is_date": False,
            }
        ]
    }
    display = {
        "columns": [
            {
                "name": "cust_tx_cnt_q1",
                "label": "Customer Transaction Count (Q1)",
                "description": "Number of customer transactions in Q1.",
            }
        ],
        "charts": [
            {
                "id": "abc123",
                "title": "Customer Transactions in Q1",
                "description": "Q1 transaction volume.",
            }
        ],
    }
    charts = [
        {
            "id": "abc123",
            "type": "histogram",
            "title": "cust_tx_cnt_q1 distribution",
            "description": None,
            "xAxis": "cust_tx_cnt_q1",
            "yAxis": "count",
            "series": ["cust_tx_cnt_q1"],
            "echarts_option": {
                "xAxis": {"type": "category", "name": "cust_tx_cnt_q1"},
                "yAxis": {"type": "value", "name": "Count"},
                "series": [{"type": "bar", "name": "cust_tx_cnt_q1"}],
            },
        }
    ]

    updated_stats = apply_display_metadata_to_statistics(statistics, display)
    updated_charts = apply_display_metadata_to_charts(charts, display)

    assert updated_stats["schema"][0]["display_label"] == "Customer Transaction Count (Q1)"
    assert updated_charts[0]["title"] == "Customer Transactions in Q1"
    assert updated_charts[0]["echarts_option"]["xAxis"]["name"] == "Customer Transaction Count (Q1)"
