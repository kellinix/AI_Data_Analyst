from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROFILE_VERSION = "1.0"


def build_data_profile_schema(
    *,
    analysis_id: str,
    file_name: str,
    statistics: dict[str, Any],
    kpis: list[dict[str, Any]],
    charts: list[dict[str, Any]],
    forecasts: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    upload_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the lightweight Profile JSON used as the AI source of truth."""
    schema = statistics.get("schema", [])
    numeric_stats = statistics.get("numeric_stats", {})
    categorical_stats = statistics.get("categorical_stats", {})

    profile = {
        "profile_version": PROFILE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "analysis_id": analysis_id,
        "dataset": {
            "name": file_name,
            "row_count": statistics.get("row_count"),
            "column_count": statistics.get("column_count"),
            "parser": statistics.get("parser", {}),
        },
        "columns": [
            _column_profile(column, numeric_stats, categorical_stats)
            for column in schema
        ],
        "metrics": {
            "kpis": [_compact_kpi(kpi) for kpi in kpis],
            "numeric_statistics": _compact_numeric_stats(numeric_stats),
            "correlations": statistics.get("correlations", {}),
            "forecasts": forecasts[:5],
            "anomalies": anomalies[:10],
        },
        "categories": {
            column: {
                "unique_count": stats.get("unique_count"),
                "top_values": stats.get("top_values", [])[:10],
            }
            for column, stats in list(categorical_stats.items())[:30]
        },
        "data_quality": statistics.get("data_quality", {}),
        "relationships": _relationship_profile(upload_context),
        "cleaning": _cleaning_profile(upload_context),
        "semantic_display": statistics.get("semantic_display", {}),
        "recommended_charts": [_compact_chart(chart) for chart in charts[:10]],
        "recommendation_candidates": recommendations[:8],
    }
    return _json_safe(profile)


def write_data_profile_schema(profile: dict[str, Any], output_path: str | Path) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return str(path)


def _column_profile(
    column: dict[str, Any],
    numeric_stats: dict[str, Any],
    categorical_stats: dict[str, Any],
) -> dict[str, Any]:
    name = column.get("name")
    profile = {
        "name": name,
        "dtype": column.get("dtype"),
        "nullable": column.get("nullable"),
        "is_numeric": column.get("is_numeric"),
        "is_date": column.get("is_date"),
        "semantic_type": column.get("semantic_type"),
        "semantic_confidence": column.get("semantic_confidence"),
        "analysis_role": column.get("analysis_role"),
        "display_label": column.get("display_label"),
        "display_description": column.get("display_description"),
    }

    if name in numeric_stats:
        stats = numeric_stats[name]
        profile["numeric_summary"] = {
            "count": stats.get("count"),
            "null_count": stats.get("null_count"),
            "min": stats.get("min"),
            "max": stats.get("max"),
            "mean": stats.get("mean"),
            "std": stats.get("std"),
            "p25": stats.get("p25"),
            "p50": stats.get("p50"),
            "p75": stats.get("p75"),
            "total": stats.get("total"),
        }

    if name in categorical_stats:
        stats = categorical_stats[name]
        profile["categorical_summary"] = {
            "unique_count": stats.get("unique_count"),
            "top_values": stats.get("top_values", [])[:10],
        }

    return profile


def _compact_numeric_stats(numeric_stats: dict[str, Any]) -> dict[str, Any]:
    return {
        column: {
            "count": stats.get("count"),
            "null_count": stats.get("null_count"),
            "min": stats.get("min"),
            "max": stats.get("max"),
            "mean": stats.get("mean"),
            "p50": stats.get("p50"),
            "total": stats.get("total"),
        }
        for column, stats in list(numeric_stats.items())[:30]
    }


def _compact_kpi(kpi: dict[str, Any]) -> dict[str, Any]:
    return {
        "column": kpi.get("column"),
        "type": kpi.get("kpi_type"),
        "value": kpi.get("value"),
        "is_total": kpi.get("is_total"),
        "is_currency": kpi.get("is_currency"),
        "mean": kpi.get("mean"),
        "count": kpi.get("count"),
    }


def _compact_chart(chart: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": chart.get("id"),
        "type": chart.get("type"),
        "title": chart.get("title"),
        "description": chart.get("description"),
        "xAxis": chart.get("xAxis"),
        "yAxis": chart.get("yAxis"),
        "series": chart.get("series", []),
        "visual_spec": chart.get("visual_spec"),
    }


def _relationship_profile(upload_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(upload_context, dict):
        return {}
    return {
        "analysis_mode": upload_context.get("analysis_mode"),
        "combine_strategy": upload_context.get("combine_strategy"),
        "combined": upload_context.get("combined", False),
        "data_description": upload_context.get("data_description"),
        "instructions": upload_context.get("instructions"),
        "suggestions": upload_context.get("suggestions", [])[:10],
        "source_files": upload_context.get("source_files", []),
    }


def _cleaning_profile(upload_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(upload_context, dict):
        return {"enabled": False}
    cleaning = upload_context.get("cleaning")
    if not isinstance(cleaning, dict):
        return {"enabled": False}
    return {
        "enabled": cleaning.get("enabled", False),
        "mode": cleaning.get("mode"),
        "report": cleaning.get("report", {}),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
