from __future__ import annotations

"""
KPI Detector — Identifies business KPIs from column names and statistics.
Never asks the user. Automatically infers what matters.
"""

from typing import Any

# Keyword maps for KPI detection
REVENUE_KEYWORDS = ["revenue", "sales", "income", "turnover", "gross", "net_revenue", "total_sales", "amount", "price", "value", "gmv"]
PROFIT_KEYWORDS = ["profit", "margin", "earnings", "ebitda", "net_income", "operating_income", "gross_profit"]
ORDER_KEYWORDS = ["orders", "transactions", "purchases", "bookings", "invoices", "deals", "quantity", "units_sold"]
CUSTOMER_KEYWORDS = ["customers", "users", "clients", "accounts", "buyers", "visitors", "leads", "contacts"]
CONVERSION_KEYWORDS = ["conversion", "cvr", "conversion_rate", "win_rate", "close_rate"]
GROWTH_KEYWORDS = ["growth", "growth_rate", "change", "yoy", "mom", "trend"]
CHURN_KEYWORDS = ["churn", "churn_rate", "cancellations", "attrition", "lost_customers"]
RETURN_KEYWORDS = ["returns", "refunds", "return_rate", "rma", "cancelled"]
COST_KEYWORDS = ["cost", "expense", "cogs", "opex", "spend", "budget"]
INVENTORY_KEYWORDS = ["inventory", "stock", "quantity_on_hand", "backorder", "units"]
MARGIN_KEYWORDS = ["margin", "gross_margin", "net_margin"]
AOV_KEYWORDS = ["aov", "average_order_value", "avg_order_value", "basket_size"]
RETENTION_KEYWORDS = ["retention", "renewal", "repeat_purchase", "repeat_rate"]
MRR_KEYWORDS = ["mrr", "monthly_recurring_revenue"]
ARR_KEYWORDS = ["arr", "annual_recurring_revenue"]
ASSET_VALUE_KEYWORDS = ["market_value", "valuation"]
MATCH_CONTEXT_METRIC_NAMES = {"goals_team", "goals_opponent"}
PERFORMANCE_COUNT_KEYWORDS = [
    "goals", "assists", "shots", "passes", "tackles", "interceptions",
    "clearances", "blocks", "recoveries", "saves", "crosses", "dribbles",
    "duels", "fouls", "offsides", "accelerations", "decelerations",
]
DURATION_KEYWORDS = ["minutes_played", "minutes", "distance_covered", "sprint_distance"]
AVERAGE_METRIC_KEYWORDS = [
    "accuracy", "rating", "score", "percentage", "percent", "pct", "rate",
    "ratio", "speed", "stamina", "impact", "resistance", "creativity",
    "consistency",
]
NON_KPI_NUMERIC_KEYWORDS = [
    "date", "time", "timestamp", "age", "height", "weight", "jersey",
    "shirt_number", "squad_number", "latitude", "longitude", "coord",
]


def detect_kpis(
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Return a list of detected KPIs with their values and metadata.
    """
    kpis = []
    matched_cols: set[str] = set()

    for col_info in schema:
        if not col_info["is_numeric"]:
            continue
        if not _is_metric_role(col_info):
            continue
        col = col_info["name"]
        col_lower = col.lower().replace(" ", "_")
        if _is_non_kpi_numeric(col_lower):
            continue
        stats = numeric_stats.get(col, {})
        total = stats.get("total")
        mean = stats.get("mean")
        count = stats.get("count", 0)

        if total is None and mean is None:
            continue

        kpi_type = _classify_column(col_lower)
        if kpi_type and col not in matched_cols:
            matched_cols.add(col)
            use_mean = _uses_average(col_lower, kpi_type)
            kpis.append({
                "column": col,
                "kpi_type": kpi_type,
                "value": mean if use_mean and mean is not None else total if total is not None else mean,
                "is_total": not use_mean and total is not None,
                "is_currency": _is_currency(col_lower),
                "mean": mean,
                "count": count,
            })

    if not kpis:
        kpis.extend(_fallback_kpis(schema, numeric_stats))

    # Sort by importance
    priority = {
        "revenue": 0, "arr": 1, "mrr": 2, "profit": 3, "orders": 4,
        "customers": 5, "margin": 6, "conversion": 7, "growth": 8,
        "aov": 9, "performance": 10, "asset_value": 11, "average": 12,
        "duration": 13, "retention": 14, "churn": 15, "cost": 16,
        "return": 17, "inventory": 18, "other": 19,
    }
    kpis.sort(key=lambda k: priority.get(k["kpi_type"], 9))
    return kpis[:10]


def _classify_column(col: str) -> str | None:
    for kw in ASSET_VALUE_KEYWORDS:
        if kw in col:
            return "asset_value"
    for kw in ARR_KEYWORDS:
        if kw in col:
            return "arr"
    for kw in MRR_KEYWORDS:
        if kw in col:
            return "mrr"
    for kw in REVENUE_KEYWORDS:
        if kw in col:
            return "revenue"
    for kw in MARGIN_KEYWORDS:
        if kw in col:
            return "margin"
    for kw in PROFIT_KEYWORDS:
        if kw in col:
            return "profit"
    for kw in ORDER_KEYWORDS:
        if kw in col:
            return "orders"
    for kw in CUSTOMER_KEYWORDS:
        if kw in col:
            return "customers"
    for kw in CONVERSION_KEYWORDS:
        if kw in col:
            return "conversion"
    for kw in GROWTH_KEYWORDS:
        if kw in col:
            return "growth"
    for kw in AOV_KEYWORDS:
        if kw in col:
            return "aov"
    for kw in RETENTION_KEYWORDS:
        if kw in col:
            return "retention"
    for kw in CHURN_KEYWORDS:
        if kw in col:
            return "churn"
    for kw in COST_KEYWORDS:
        if kw in col:
            return "cost"
    for kw in RETURN_KEYWORDS:
        if kw in col:
            return "return"
    for kw in INVENTORY_KEYWORDS:
        if kw in col:
            return "inventory"
    for kw in PERFORMANCE_COUNT_KEYWORDS:
        if kw in col:
            return "performance"
    for kw in DURATION_KEYWORDS:
        if kw in col:
            return "duration"
    for kw in AVERAGE_METRIC_KEYWORDS:
        if kw in col:
            return "average"
    return None


def _is_currency(col: str) -> bool:
    currency_keywords = ["revenue", "sales", "profit", "cost", "price", "amount", "income", "spend", "value", "valuation", "gmv", "mrr", "arr", "aov"]
    return any(kw in col for kw in currency_keywords)


def _uses_average(col: str, kpi_type: str) -> bool:
    return (
        kpi_type in {"margin", "conversion", "growth", "retention", "churn", "return", "average"}
        or "pct" in col
        or "percent" in col
        or "percentage" in col
        or "rate" in col
        or any(keyword in col for keyword in AVERAGE_METRIC_KEYWORDS)
    )


def _is_metric_role(col_info: dict[str, Any]) -> bool:
    role = col_info.get("analysis_role")
    return role in {None, "metric"}


def _is_non_kpi_numeric(col: str) -> bool:
    parts = set(col.split("_"))
    return (
        col in MATCH_CONTEXT_METRIC_NAMES
        or col == "year"
        or col.endswith("_year")
        or col == "id"
        or col.endswith("_id")
        or col.startswith("id_")
        or col.startswith("is_")
        or col.startswith("has_")
        or any(keyword in parts for keyword in NON_KPI_NUMERIC_KEYWORDS)
        or any(keyword in col for keyword in ("shirt_number", "squad_number"))
    )


def _fallback_kpis(
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    ranked = []
    for col_info in schema:
        if not col_info["is_numeric"]:
            continue
        if not _is_metric_role(col_info):
            continue
        col = col_info["name"]
        col_lower = col.lower().replace(" ", "_")
        if _is_non_kpi_numeric(col_lower):
            continue
        stats = numeric_stats.get(col, {})
        value = stats.get("total")
        use_mean = _uses_average(col_lower, "other")
        if use_mean:
            value = stats.get("mean")
        if value is None:
            value = stats.get("mean")
        if value is None:
            continue
        ranked.append({
            "column": col,
            "kpi_type": "other",
            "value": value,
            "is_total": not use_mean and stats.get("total") is not None,
            "is_currency": _is_currency(col.lower().replace(" ", "_")),
            "mean": stats.get("mean"),
            "count": stats.get("count", 0),
            "score": _fallback_score(col_lower, stats),
            "fallback_reason": "Highest available numeric business metric",
        })
    ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
    for item in ranked:
        item.pop("score", None)
    return ranked[:4]


def _fallback_score(col: str, stats: dict[str, Any]) -> float:
    score = 0.0
    if _uses_average(col, "other"):
        score += 35
    if any(keyword in col for keyword in PERFORMANCE_COUNT_KEYWORDS):
        score += 30
    if any(keyword in col for keyword in DURATION_KEYWORDS):
        score += 12
    if _is_currency(col):
        score += 10
    non_null = float(stats.get("count") or 0)
    score += min(non_null / 1000, 5)
    return score
