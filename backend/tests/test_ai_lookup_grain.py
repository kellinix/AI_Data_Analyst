from app.services.ai_service import AIService


def test_fallback_ai_summary_omits_repeated_lookup_statistics_and_weights():
    stats = {
        "row_count": 4, "column_count": 3,
        "schema": [
            {"name": "quantity", "is_numeric": True, "analysis_role": "metric"},
            {"name": "margin", "is_numeric": True, "analysis_role": "metric"},
            {"name": "freight", "is_numeric": True, "analysis_role": "metric",
             "measure_grain": {"kind": "lookup", "repeated": True, "source_table": "orders.csv"}},
        ],
        "numeric_stats": {
            "quantity": {"mean": 2, "min": 1, "max": 3, "total": 8},
            "margin": {"mean": 10, "min": 5, "max": 15, "total": 40},
            "freight": {"mean": 999, "min": 999, "max": 999, "total": 3996},
        },
    }
    kpis = [{"column": "freight", "value": 3996},
            {"column": "margin", "value": 8765, "weighted_by": "freight"},
            {"column": "quantity", "value": 8}]
    text = AIService()._build_stats_summary(stats, kpis)
    assert "quantity" in text and "freight" not in text
    assert "3996" not in text and "8765" not in text
    assert stats["numeric_stats"]["freight"]["total"] == 3996
