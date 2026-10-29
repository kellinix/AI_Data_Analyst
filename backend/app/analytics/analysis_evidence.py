"""Measured context and disclosures shared by every analysis consumer."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.analytics.category_values import normalized_geography


def analysis_evidence(statistics: dict[str, Any], upload_context: Any) -> dict[str, Any]:
    cleaning = upload_context.get("cleaning", {}) if isinstance(upload_context, dict) else {}
    if not isinstance(cleaning, dict):
        cleaning = {}
    report = cleaning.get("report") or {}
    from app.analytics.record_context import record_context

    context = record_context(statistics)
    noun = (context or {}).get("plural", "records")
    notes = [f"Counts describe {noun} unless a count of different names or IDs is clearly stated."]
    if any(normalized_geography(c["name"]) for c in statistics.get("schema", [])):
        notes.append("Geographic groups combine case, spacing and hyphen variants; source values are preserved and names are not verified against an external geographic reference.")
    if not statistics.get("date_range") and not any(c.get("analysis_role") == "temporal_dimension" for c in statistics.get("schema", [])):
        notes.append(
            "No usable date series was detected; this file alone cannot establish growth or change over time."
        )
    recorded_dates = []
    for bounds in (statistics.get("date_range") or {}).values():
        if not isinstance(bounds, dict) or not bounds.get("max"):
            continue
        try:
            recorded_dates.append(date.fromisoformat(str(bounds["max"])[:10]))
        except ValueError:
            continue
    if recorded_dates and (date.today() - max(recorded_dates)).days > 120:
        notes.append(
            f"The latest recorded date is {max(recorded_dates):%d %b %Y}. "
            "These figures are too old for a current forward-looking forecast."
        )
    if not any(c.get("analysis_role") == "metric" for c in statistics.get("schema", [])):
        notes.append(
            "Category frequencies describe the composition of this file, not demand, performance or outcomes."
        )
    if statistics.get("sample_truncated"):
        notes.append(
            f"Results cover the first {statistics.get('sample_row_limit'):,} records, not the full file."
        )
    optional_note = (statistics.get("data_quality") or {}).get("optional_fields_note")
    if optional_note:
        notes.append(optional_note)
    changes = []
    for sheet in statistics.get("parser", {}).get("excluded_sheets", []):
        notes.append(
            f"Worksheet {sheet['name']} was kept separate because it does not list the same type of {noun}."
        )
    removal_keys = {
        "dropped_empty_rows": "Empty records removed",
        "dropped_rows_missing_critical_metrics": "Records without required measures removed",
        "removed_duplicate_rows": "Exact duplicates removed after normalization",
        "removed_fuzzy_duplicate_rows": "Similar records removed by fuzzy matching",
        "excluded_outlier_rows": "Extreme records excluded",
    }
    for key, label in removal_keys.items():
        count = int(report.get(key) or 0)
        if count:
            changes.append({"reason": label, "rows": count})
    provenance = {}
    if cleaning.get("enabled") and "input_rows" in report and "output_rows" in report:
        before, after = int(report["input_rows"]), int(report["output_rows"])
        unexplained = before - after - sum(item["rows"] for item in changes)
        provenance = {
            "input_rows": before,
            "output_rows": after,
            "removed_rows": before - after,
            "row_changes": changes,
            "unexplained_row_change": unexplained,
            "reconciled": unexplained == 0,
        }
        if before != after:
            notes.append(
                f"Cleaning changed the file from {before:,} to {after:,} {noun}; counts use the cleaned file."
            )
        if unexplained:
            notes.append(
                f"The cleaning report does not explain a net change of {unexplained:,} records; review it before relying on totals."
            )
    missing = report.get("missing_values") or {}
    for item in [
        *missing.get("numeric_imputations", []),
        *missing.get("categorical_imputations", []),
    ]:
        count = int(item.get("filled") or 0)
        if count:
            notes.append(
                f"{item.get('column')}: {count:,} missing values replaced using {item.get('method')}; these are not observed values."
            )
    if report.get("capped_outlier_values"):
        notes.append(
            f"{report['capped_outlier_values']:,} extreme values were capped; totals and averages may differ from the source."
        )
    return {
        "count_basis": "records",
        "entity_counts": statistics.get("entity_counts", []),
        "limitations": notes,
        "cleaning": provenance,
    }


def recommendation_catalogue(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only server-computed actions may be ranked by the model."""
    return [{"id": f"action_{index}", "recommendation": recommendation}
            for index, recommendation in enumerate(recommendations)]


def select_recommendations(
    requested_ids: Any, catalogue: list[dict[str, Any]],
    free_form: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_id = {item["id"]: item["recommendation"] for item in catalogue}
    requested = requested_ids if isinstance(requested_ids, list) else []
    valid = list(dict.fromkeys(id for id in requested if isinstance(id, str) and id in by_id))
    rejected = [id for id in requested if not isinstance(id, str) or id not in by_id]
    ordered = [*valid, *(id for id in by_id if id not in valid)]
    return [by_id[id] for id in ordered], {
        "method": "measured_actions_v1", "free_form_used": False,
        "selection": "ai_ranked" if valid else "deterministic",
        "selected_ids": ordered, "rejected_ids": rejected,
        "rejected_free_form_count": len(free_form or []),
    }
