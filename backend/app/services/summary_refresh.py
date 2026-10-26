"""Update an older summary using saved measurements, with no AI request."""

from __future__ import annotations

from typing import Any

from app.analytics.summary_evidence import build_summary_facts, render_summary


def saved_measurements(analysis: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Reconstruct measured inputs without trusting saved narrative text."""
    metadata = dict(analysis.metadata_ or {})
    profile = metadata.get("data_profile")
    if not isinstance(profile, dict) or not profile.get("columns"):
        raise ValueError("This analysis has no saved data profile. Re-analyse it to rebuild the summary.")
    evidence = dict(metadata.get("analysis_evidence") or {})
    dataset = profile.get("dataset") or {}
    metrics = profile.get("metrics") or {}
    schema = metadata.get("schema") or profile["columns"]
    numeric = {column["name"]: dict(column["numeric_summary"])
               for column in profile["columns"] if column.get("numeric_summary")}
    for name, values in (metrics.get("numeric_statistics") or {}).items():
        numeric[name] = {**numeric.get(name, {}), **values}
    statistics = {
        "row_count": analysis.row_count, "column_count": analysis.column_count,
        "schema": schema, "numeric_stats": numeric,
        "categorical_stats": profile.get("categories") or {},
        "date_range": metadata.get("date_range") or {},
        "entity_counts": evidence.get("entity_counts") or [],
        "analysis_evidence": evidence,
        "data_quality": metadata.get("data_quality") or profile.get("data_quality") or {},
        "sample_truncated": dataset.get("sample_truncated", False),
    }
    kpis = [dict(insight.data) for insight in analysis.insights
            if insight.type == "summary" and isinstance(insight.data, dict)]
    currency = metadata.get("currency") or {}
    for kpi in kpis:
        if kpi.get("is_currency") and currency.get("symbol"):
            kpi["currency_symbol"] = currency["symbol"]
    statistics["forecasts"] = metadata.get("forecasts") or metrics.get("forecasts") or []
    return statistics, kpis


def refresh_saved_summary(analysis: Any) -> dict[str, Any]:
    statistics, kpis = saved_measurements(analysis)
    metadata = dict(analysis.metadata_ or {})
    profile = metadata["data_profile"]
    evidence = dict(metadata.get("analysis_evidence") or {})
    facts = build_summary_facts(statistics, kpis, statistics["forecasts"],
                                metadata.get("upload_context"))
    summary, checks = render_summary(facts)
    if (evidence.get("summary_checks") or {}).get("method") != "measured_facts_v1":
        metadata.setdefault("summary_previous", analysis.summary)
    evidence["summary_fact_catalogue"] = facts
    evidence["summary_checks"] = checks
    analysis.summary = summary
    analysis.metadata_ = {**metadata, "analysis_evidence": evidence,
                          "data_profile": {**profile, "analysis_evidence": evidence}}
    return {"summary": summary, "analysis_evidence": evidence}
