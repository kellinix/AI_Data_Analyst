"""Render summary claims from measured facts rather than unverified prose."""

from __future__ import annotations

import math
from typing import Any

from app.analytics.semantic_detector import is_serial_identifier


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _format(value: float) -> str:
    if 0 < abs(value) < .01:
        return f"{value:.4g}"
    return f"{value:,.2f}".rstrip("0").rstrip(".") if not value.is_integer() else f"{value:,.0f}"


def build_summary_facts(
    statistics: dict[str, Any], kpis: list[dict[str, Any]],
    forecasts: list[dict[str, Any]] | None = None,
    upload_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """A bounded catalogue of canonical claims and their calculation provenance.

    The model may rank these IDs, but cannot change a statement's values,
    aggregation, subject, denominator or qualification.
    """
    facts: list[dict[str, Any]] = []
    rows = int(statistics.get("row_count") or 0)
    fields = int(statistics.get("column_count") or len(statistics.get("schema", [])))
    schema = {c["name"]: c for c in statistics.get("schema", [])}
    from app.analytics.record_context import record_context

    sales_file = (record_context(statistics) or {}).get("kind") == "sales_transaction"
    evidence = statistics.get("analysis_evidence") or {}
    sampled = bool(statistics.get("sample_truncated"))
    scope = "analysed sample" if sampled else "analysed file"

    def label(column: str) -> str:
        if sales_file and column in {"money", "total"}:
            return "Sales Amount"
        if sales_file and column == "cash_type":
            return "Payment Method"
        fallback = column.replace("_", " ")
        display = str(schema.get(column, {}).get("display_label") or "")
        # Display metadata can be model-assisted. Accept formatting changes,
        # not a new business meaning such as relabelling revenue as profit.
        def normalized(value: str) -> str:
            return "".join(c for c in value.casefold() if c.isalnum())
        return display if display and normalized(display) == normalized(column) else fallback[:1].upper() + fallback[1:]

    def add(id: str, text: str, source: str, calculation: str,
            values: dict[str, Any], priority: int, required: bool = False) -> None:
        facts.append({"id": id, "text": text, "source": source, "calculation": calculation,
                      "values": values, "scope": scope, "priority": priority, "required": required})

    count_text = f"The analysis covers {rows:,} records across {fields:,} fields"
    if sampled:
        count_text += ", using the first records imported from the file rather than its full contents"
    add("records", count_text + ".", "statistics.row_count; statistics.column_count",
        "Count of analysed records and fields", {"records": rows, "fields": fields, "sampled": sampled}, 0, True)

    cleaning = evidence.get("cleaning") or {}
    if cleaning.get("removed_rows", 0) > 0:
        before, after = cleaning["input_rows"], cleaning["output_rows"]
        text = f"Cleaning reduced {before:,} input records to {after:,}; all figures here describe the cleaned file."
        if not cleaning.get("reconciled"):
            text += " The cleaning report does not explain every removed record."
        add("cleaning", text, "analysis_evidence.cleaning", "Input count minus output count",
            dict(cleaning), 1, True)

    context = upload_context if isinstance(upload_context, dict) else {}
    report = ((context.get("cleaning") or {}).get("report") or {})
    missing = report.get("missing_values") or {}
    replacements = [*missing.get("numeric_imputations", []), *missing.get("categorical_imputations", [])]
    filled = sum(int(item.get("filled") or 0) for item in replacements)
    if filled:
        add("imputation", f"Cleaning filled {filled:,} missing cells; those replacements are not observed values.",
            "upload_context.cleaning.report.missing_values", "Sum of filled cells across fields",
            {"filled_cells": filled, "fields": replacements}, 1, True)
    capped = int(report.get("capped_outlier_values") or 0)
    if capped:
        add("capping", f"Cleaning capped {capped:,} extreme values, so totals and averages may differ from the source.",
            "upload_context.cleaning.report.capped_outlier_values", "Count of capped values",
            {"capped_values": capped}, 1, True)

    quality = statistics.get("data_quality") or {}
    source_quality = quality.get("source_quality") or {}
    source_issues = source_quality.get("issues") or quality.get("issues") or []
    renamed = report.get("renamed_columns") or {}
    gaps = [issue for issue in source_issues if issue.get("type") == "missing_values"
            and schema.get(renamed.get(issue.get("column"), issue.get("column")), {}).get("analysis_role") != "identifier"
            and max(1, rows * .1) <= int(issue.get("affected_rows") or 0) < int(report.get("input_rows") or rows)]
    if gaps:
        issue = max(gaps, key=lambda item: int(item.get("affected_rows") or 0))
        column, missing_count = str(issue.get("column")), int(issue["affected_rows"])
        location = "source file" if source_quality else "analysed file"
        add("missing", f"{label(renamed.get(column, column))} has {missing_count:,} missing values in the {location}; confirm whether that field is required.",
            "data_quality.source_quality.issues" if source_quality else "data_quality.issues",
            "Missing-value count for this field", {"column": column, "missing_values": missing_count}, 1, True)

    for index, kpi in enumerate(kpis[:8]):
        column = str(kpi.get("column") or "")
        role = schema.get(column, {}).get("analysis_role")
        value = _finite(kpi.get("value"))
        stats = statistics.get("numeric_stats", {}).get(column, {})
        if role not in {"metric", "flag"} or value is None:
            continue
        weighted = kpi.get("weighted_by")
        operation = "weighted_mean" if weighted else "mean" if not kpi.get("is_total", True) else "total"
        measured = _finite(stats.get(operation))
        if measured is None:
            continue
        if kpi.get("is_percent"):
            measured *= 100
        if not math.isclose(value, measured, rel_tol=1e-9, abs_tol=.051 if kpi.get("is_percent") else 1e-9):
            continue
        formatted = _format(value)
        if kpi.get("is_percent") or any(token in column.lower() for token in ("%", "pct", "percent")):
            formatted += "%"
        elif kpi.get("is_currency") and kpi.get("currency_symbol"):
            formatted = str(kpi["currency_symbol"]) + formatted
        if weighted:
            text = f"{label(column)} averages {formatted} when weighted by {label(str(weighted))}."
            calculation = f"SUM({column} * {weighted}) / SUM({weighted}), using supplied values and positive supplied weights"
        else:
            verb = "sums to" if operation == "total" else "averages"
            count = int(stats.get("count") or 0)
            text = f"{label(column)} {verb} {formatted} across {count:,} supplied values."
            calculation = f"{'SUM' if operation == 'total' else 'AVG'}({column})" + (" * 100" if kpi.get("is_percent") else "")
        add(f"metric_{index}", text, f"numeric_stats.{column}.{operation}", calculation,
            {"column": column, "value": value, "operation": operation, "weighted_by": weighted,
             "display_value": formatted, "display_label": label(column)}, 2 if index < 2 else 4)

    entities = [entity for entity in statistics.get("entity_counts", [])
                if not is_serial_identifier(str(entity["column"]))][:3]
    for index, entity in enumerate(entities):
        column = str(entity["column"])
        count = int(entity["distinct_values"])
        add(f"identity_{index}", f"{label(column)} contains {count:,} distinct recorded values; real-world identity is not verified.",
            f"entity_counts.{column}", "COUNT(DISTINCT supplied values), excluding blank and Unknown labels",
            dict(entity), 3)

    category_index = 0
    for column, category in statistics.get("categorical_stats", {}).items():
        if schema.get(column, {}).get("analysis_role") not in {"dimension", "flag"} or rows <= 0:
            continue
        top = [item for item in category.get("top_values", [])
               if 0 < int(item.get("count") or 0) <= rows]
        if not top:
            continue
        item = max(top, key=lambda item: item["count"])
        count = int(item["count"])
        add(f"category_{category_index}", f"{label(column)} has {count:,} records labelled '{item['value']}' ({count / rows:.1%} of all {rows:,} analysed records).",
            f"categorical_stats.{column}.top_values", "Category count / all analysed records * 100",
            {"column": column, "category": item["value"], "count": count, "denominator": rows,
             "percent": count / rows * 100, "display_label": label(column)}, 3)
        category_index += 1
        if category_index >= 4:
            break

    for index, forecast in enumerate(forecasts or []):
        latest = _finite(forecast.get("latest_value"))
        interval = forecast.get("predictions", {}).get("next_month", {})
        low, high = _finite(interval.get("lower")), _finite(interval.get("upper"))
        if latest is None or low is None or high is None or not low <= latest <= high:
            continue
        column = str(forecast.get("metric") or "")
        add(f"forecast_{index}", f"For {label(column)}, the next-month model range of {_format(low)} to {_format(high)} includes the latest month's {_format(latest)}; the direction of change is uncertain.",
            f"forecasts.{index}.predictions.next_month", "Compare latest monthly value with next-month model range",
            {"column": column, "latest": latest, "lower": low, "upper": high,
             "method": forecast.get("method"), "observations": forecast.get("observations"),
             "display_label": label(column)}, 3)

    if not statistics.get("date_range") and not any(c.get("analysis_role") == "temporal_dimension" for c in schema.values()):
        add("snapshot", "No usable date series was detected, so this file cannot establish growth or change over time.",
            "statistics.date_range; statistics.schema", "Check for a usable temporal field", {}, 3)
    return facts


def render_summary(
    facts: list[dict[str, Any]], requested_ids: Any = None,
) -> tuple[str, dict[str, Any]]:
    """Choose known facts only; mandatory scope/cleaning qualifications survive ranking."""
    by_id = {fact["id"]: fact for fact in facts}
    requested = requested_ids if isinstance(requested_ids, list) else []
    valid = list(dict.fromkeys(item for item in requested if isinstance(item, str) and item in by_id))
    rejected = [item for item in requested if not isinstance(item, str) or item not in by_id]
    chosen = [fact["id"] for fact in facts if fact["required"]]
    ranked = sorted(facts, key=lambda fact: fact["priority"])
    for id in [*valid, *(fact["id"] for fact in ranked)]:
        if id not in chosen and len(chosen) < 5:
            chosen.append(id)
    selected = [by_id[id] for id in chosen]
    return "\n".join(fact["text"] for fact in selected), {
        "method": "measured_facts_v1", "free_form_used": False,
        "selection": "ai_ranked" if valid else "deterministic",
        "rejected_fact_ids": rejected, "facts": selected,
    }
