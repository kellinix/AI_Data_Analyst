"""
Deterministic recommendation generation from measured evidence.

These recommendations give the product useful output even when AI generation is
unavailable, and they constrain the LLM to evidence-backed opportunities.
"""

from __future__ import annotations

from typing import Any

from app.analytics.calibration import (
    RULE_ANOMALY,
    RULE_DATA_QUALITY,
    RULE_FORECAST,
    RULE_TRACKING,
    confidence_fields,
)
from app.analytics.labels import sentence_label
from app.analytics.semantic_detector import is_serial_identifier
from app.analytics.text_matching import contains_keyword, shorten_label


def generate_recommendations(
    *,
    kpis: list[dict[str, Any]],
    data_quality: dict[str, Any],
    anomalies: list[dict[str, Any]],
    forecasts: list[dict[str, Any]],
    statistics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    recommendations.extend(_quality_recommendations(data_quality))
    source = data_quality.get("source_quality", {})
    source_rows = int(source.get("input_rows") or 0)
    material_source_issues = [
        issue for issue in source.get("issues", [])
        if not source_rows or int(issue.get("affected_rows") or 0) / source_rows >= 0.1
    ]
    if material_source_issues:
        issue = max(material_source_issues, key=lambda item: item.get("affected_rows", 0))
        evidence = f"{issue.get('column')}: {issue.get('description')}"
        recommendations.append({
            "title": f"Check source coverage for {_humanize(issue.get('column') or 'missing fields')}",
            "description": "Confirm whether this field is optional. Compare results for populated and missing records before using it to rank or target groups.",
            "problem": "Cleaning can fill gaps without restoring the missing information.",
            "evidence": evidence, "expected_impact": "Makes the coverage limits of comparisons explicit.",
            "financial_opportunity": None, "importance": "medium", **confidence_fields(RULE_DATA_QUALITY),
            "data": {"evidence": evidence, "owner": "Data Operations", "difficulty": "Easy"},
        })
    recommendations.extend(_forecast_recommendations(forecasts, kpis))
    recommendations.extend(_anomaly_recommendations(anomalies))
    recommendations.extend(_counting_recommendations(statistics or {}))

    if not recommendations and kpis:
        top_kpi = kpis[0]
        label = _humanize(top_kpi["column"])
        recommendations.append({
            "title": f"Track {label} regularly",
            "description": f"Use {label.lower()} as a standing measure in the next review cycle.",
            "problem": "A measured value alone does not establish a target or a change over time.",
            "evidence": f"{label} is {_format_value(top_kpi.get('value'))}.",
            "expected_impact": "Helps decision-makers spot movement in an important measure earlier.",
            "financial_opportunity": None,
            "importance": "medium",
            **confidence_fields(RULE_TRACKING),
            "data": {
                "difficulty": "Easy",
                "owner": "Operations",
                "estimated_completion": "1 week",
                "show_financial_opportunity": False,
            },
        })

    return recommendations[:8]


def _counting_recommendations(statistics: dict[str, Any]) -> list[dict[str, Any]]:
    """Repeated entities are a counting limitation, not evidence of poor performance."""
    for measure in statistics.get("entity_counts", []):
        if is_serial_identifier(str(measure.get("column") or "")):
            continue
        populated = measure.get("populated_records", 0)
        repeated = measure.get("repeated_records", 0)
        if populated and repeated / populated >= 0.05:
            column = measure["column"]
            evidence = (f"{populated:,} records contain {measure['distinct_values']:,} distinct values in {column}; "
                        f"{repeated:,} records repeat an already recorded value.")
            return [{
                "title": f"Use distinct {_humanize(column)} counts for entity comparisons",
                "description": "Compare record counts with distinct-value counts before ranking groups. Verify the identity field before treating distinct values as unique entities.",
                "problem": "One entity may appear in several records, so row counts can overstate entity coverage.",
                "evidence": evidence, "expected_impact": "Avoids confusing activity or register entries with the number of entities represented.",
                "financial_opportunity": None, "importance": "medium",
                **confidence_fields(RULE_DATA_QUALITY),
                "data": {"column": column, "evidence": evidence, "owner": "Data Operations", "difficulty": "Easy"},
            }]
    return []


def _quality_recommendations(data_quality: dict[str, Any]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    issues = data_quality.get("issues", [])
    high_impact = [issue for issue in issues if issue.get("severity") in {"high", "critical"}]
    if high_impact:
        issue = high_impact[0]
        column = issue.get("column")
        description = issue.get("description", "Severe data quality issue detected.")
        # Name the column: "78.2% of values are missing" alone doesn't say which field.
        problem = f"{_humanize(column)}: {description}" if column else description
        recs.append({
            "title": "Review high-impact data quality checks",
            "description": "Confirm which fields are required and when missing values are expected. Compare populated and missing groups before using incomplete fields in decisions.",
            "problem": problem,
            "evidence": problem,
            "expected_impact": "Higher confidence in KPIs, forecasts, and executive reporting.",
            "financial_opportunity": None,
            "importance": "high",
            **confidence_fields(RULE_DATA_QUALITY),
            "data": {
                "difficulty": "Medium",
                "owner": "Data Operations",
                "evidence": problem,
                "column": column,
            },
        })
    return recs


def _forecast_recommendations(
    forecasts: list[dict[str, Any]],
    kpis: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []

    for forecast in forecasts:
        if forecast.get("change_direction_supported") is False:
            continue
        interval = forecast.get("predictions", {}).get("next_month", {})
        lower, upper = interval.get("lower"), interval.get("upper")
        latest = forecast.get("latest_value")
        if lower is not None and upper is not None and latest is not None and lower <= latest <= upper:
            continue
        change = forecast.get("change_percent_next_month", 0)
        metric = forecast["metric"]
        label = _humanize(metric)
        if abs(change) < 5:
            continue
        direction = "increase" if change > 0 else "decline"
        owner = (
            "Revenue Operations"
            if any(word in metric.lower() for word in ("revenue", "sales", "arr", "mrr"))
            else "Operations"
        )
        recs.append({
            "title": f"Prepare for {label} {direction}",
            "description": f"The next-month forecast suggests {label.lower()} may {direction} by {abs(change):.1f}%.",
            "problem": f"{label} is projected to move materially next month.",
            "evidence": f"Latest value {forecast['latest_value']:,.2f}; forecast {forecast['predictions']['next_month']['value']:,.2f}.",
            "expected_impact": "Better capacity, budget, and commercial planning before the change lands.",
            "financial_opportunity": None,
            "importance": "high" if abs(change) >= 15 else "medium",
            **confidence_fields(RULE_FORECAST, default=forecast.get("confidence", 0.7)),
            "data": {
                "difficulty": "Medium",
                "owner": owner,
                "column": metric,
                "estimated_completion": "2 weeks",
                "expected_impact": f"Plan around a projected {abs(change):.1f}% {direction}.",
                "evidence": f"{forecast['observations']} monthly observations support the forecast.",
                "show_financial_opportunity": False,
            },
        })
    return recs


def _anomaly_recommendations(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not anomalies:
        return []
    anomaly = anomalies[0]
    label = _humanize(anomaly["column"])
    context = anomaly.get("context") or {}
    # Shortened, as the anomaly's own description already is: this built its
    # context string separately, so the recommendation still carried 200
    # characters of "Ipa Delivery Confidence Assessment A Delivery Confidence
    # Assessment Of The Project At A Fixed Point In Time..." before the value.
    context_text = ", ".join(
        f"{shorten_label(_humanize(k), 40)} {v}" for k, v in context.items()
    )
    return [{
        "title": f"Look into the unusual {label}",
        "description": (
            f"Compare this one ({context_text}) with similar ones to see what drove it."
            if context_text
            else f"Compare this {sentence_label(label)} entry with similar ones before drawing a conclusion."
        ),
        "problem": anomaly.get("description", f"One {label} result is much higher than usual."),
        "evidence": anomaly.get("description", f"One {label} result is much higher than usual."),
        # This read "...or a one-off match moment" — sports copy left in a
        # template, shown to someone reading a government project portfolio.
        "expected_impact": "Tells you whether this is a genuine result worth repeating, a pattern, or a one-off.",
        "financial_opportunity": None,
        "importance": "medium",
        **confidence_fields(RULE_ANOMALY),
        "data": {
            "difficulty": "Easy",
            "owner": _owner_for_metric(anomaly["column"]),
            "estimated_completion": "3 days",
            "evidence": anomaly.get("description"),
            "show_financial_opportunity": False,
        },
    }]


def _owner_for_metric(metric: str) -> str:
    if contains_keyword(metric, ("revenue", "sales", "profit", "cost", "arr", "mrr")):
        return "Commercial Team"
    return "Operations"


def _format_value(value: Any) -> str:
    if value is None:
        return "available in the dashboard"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(numeric) >= 1000:
        return f"{numeric:,.0f}" if numeric.is_integer() else f"{numeric:,.2f}"
    return f"{numeric:,.2f}".rstrip("0").rstrip(".")


def _humanize(value: str) -> str:
    replacements = {"pct": "%", "km": "km", "kmh": "km/h"}
    return " ".join(
        replacements.get(word.lower(), word.capitalize())
        for word in value.replace("_", " ").split()
    )
