from __future__ import annotations

"""
Deterministic recommendation generation from measured evidence.

These recommendations give the product useful output even when AI generation is
unavailable, and they constrain the LLM to evidence-backed opportunities.
"""

from typing import Any


def generate_recommendations(
    *,
    kpis: list[dict[str, Any]],
    data_quality: dict[str, Any],
    anomalies: list[dict[str, Any]],
    forecasts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    recommendations.extend(_quality_recommendations(data_quality))
    recommendations.extend(_forecast_recommendations(forecasts, kpis))
    recommendations.extend(_anomaly_recommendations(anomalies))

    if not recommendations and kpis:
        top_kpi = kpis[0]
        label = _humanize(top_kpi["column"])
        recommendations.append({
            "title": f"Track {label} regularly",
            "description": f"Use {label.lower()} as a standing measure in the next review cycle.",
            "problem": "The file contains a useful measure, but it is not yet tied to a regular review rhythm.",
            "evidence": f"{label} is {_format_value(top_kpi.get('value'))}.",
            "expected_impact": "Helps decision-makers spot movement in an important measure earlier.",
            "financial_opportunity": (
                _opportunity_from_value(top_kpi.get("value"), 0.01)
                if top_kpi.get("is_currency")
                else None
            ),
            "importance": "medium",
            "confidence": 0.72,
            "data": {
                "difficulty": "Easy",
                "owner": "Operations",
                "estimated_completion": "1 week",
                "show_financial_opportunity": bool(top_kpi.get("is_currency")),
            },
        })

    return recommendations[:8]


def _quality_recommendations(data_quality: dict[str, Any]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    issues = data_quality.get("issues", [])
    high_impact = [issue for issue in issues if issue.get("severity") in {"high", "critical"}]
    if high_impact:
        issue = high_impact[0]
        recs.append({
            "title": "Clean high-impact data quality issues",
            "description": "Resolve the most severe data quality gaps before making operational decisions from this dataset.",
            "problem": issue.get("description", "Severe data quality issue detected."),
            "evidence": f"Quality score is {data_quality.get('score', 0)}/100 with {len(issues)} detected issues.",
            "expected_impact": "Higher confidence in KPIs, forecasts, and executive reporting.",
            "financial_opportunity": None,
            "importance": "high",
            "confidence": 0.9,
            "data": {
                "difficulty": "Medium",
                "owner": "Data Operations",
                "estimated_completion": "1-2 weeks",
                "evidence": issue.get("description"),
            },
        })
    return recs


def _forecast_recommendations(
    forecasts: list[dict[str, Any]],
    kpis: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    kpi_by_column = {kpi["column"]: kpi for kpi in kpis}

    for forecast in forecasts:
        change = forecast.get("change_percent_next_month", 0)
        metric = forecast["metric"]
        label = _humanize(metric)
        if abs(change) < 5:
            continue
        kpi = kpi_by_column.get(metric, {})
        is_currency = bool(kpi.get("is_currency")) or _looks_like_currency(metric)
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
            "financial_opportunity": (
                _opportunity_from_value(kpi.get("value"), 0.03)
                if is_currency
                else None
            ),
            "importance": "high" if abs(change) >= 15 else "medium",
            "confidence": forecast.get("confidence", 0.7),
            "data": {
                "difficulty": "Medium",
                "owner": owner,
                "estimated_completion": "2 weeks",
                "expected_impact": f"Plan around a projected {abs(change):.1f}% {direction}.",
                "evidence": f"{forecast['observations']} monthly observations support the forecast.",
                "show_financial_opportunity": is_currency,
            },
        })
    return recs


def _anomaly_recommendations(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not anomalies:
        return []
    anomaly = anomalies[0]
    label = _humanize(anomaly["column"])
    return [{
        "title": f"Look into standout {label}",
        "description": "Check the players or matches behind the standout result and see what made it different from the rest.",
        "problem": anomaly.get("description", f"One {label} result is much higher than usual."),
        "evidence": anomaly.get("description", f"One {label} result is much higher than usual."),
        "expected_impact": "Helps explain whether this was exceptional performance, a tactical pattern, or a one-off match moment.",
        "financial_opportunity": None,
        "importance": "high",
        "confidence": 0.82,
        "data": {
            "difficulty": "Easy",
            "owner": _owner_for_metric(anomaly["column"]),
            "estimated_completion": "3 days",
            "evidence": anomaly.get("description"),
            "show_financial_opportunity": False,
        },
    }]


def _opportunity_from_value(value: Any, ratio: float) -> float | None:
    if value is None:
        return None
    try:
        return round(abs(float(value)) * ratio, 2)
    except (TypeError, ValueError):
        return None


def _looks_like_currency(metric: str) -> bool:
    normalized = metric.lower()
    return any(
        word in normalized
        for word in ("revenue", "sales", "profit", "cost", "price", "amount", "income", "spend", "value", "arr", "mrr")
    )


def _owner_for_metric(metric: str) -> str:
    normalized = metric.lower()
    if any(word in normalized for word in ("goal", "assist", "shot", "pass", "rating", "xg", "xa")):
        return "Performance Team"
    if any(word in normalized for word in ("revenue", "sales", "profit", "cost", "arr", "mrr")):
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
    replacements = {"xg": "xG", "xa": "xA", "pct": "%", "km": "km", "kmh": "km/h"}
    return " ".join(
        replacements.get(word.lower(), word.capitalize())
        for word in value.replace("_", " ").split()
    )
