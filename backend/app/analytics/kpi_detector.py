"""
KPI Detector — Identifies business KPIs from column names and statistics.
Never asks the user. Automatically infers what matters.
"""

from __future__ import annotations

from typing import Any

from app.analytics.text_matching import contains_keyword

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
DURATION_KEYWORDS = ["duration", "hours", "minutes", "distance", "time_to_hire", "cycle_time"]
AVERAGE_METRIC_KEYWORDS = [
    "accuracy", "rating", "score", "percentage", "percent", "pct", "rate",
    "ratio", "speed", "impact", "satisfaction", "nps",
    # Already-averaged measures: summing them compounds an average, which is
    # how a demo dashboard showed "Avg Order Value $46,919.50".
    "avg", "average", "mean", "median", "aov",
]
NON_KPI_NUMERIC_KEYWORDS = [
    "date", "time", "timestamp", "age", "latitude", "longitude", "coord",
]
# Binary flag columns whose name marks them as the outcome the dataset is
# about (e.g. "target" in a disease dataset, "churned" in a customer list).
OUTCOME_KEYWORDS = [
    "target", "outcome", "label", "churned", "converted", "survived",
    "fraud", "clicked", "purchased", "responded", "approved", "won",
    "success", "disease", "readmitted", "defaulted",
]


def detect_kpis(
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Return a list of detected KPIs with their values and metadata.
    """
    kpis = _outcome_rate_kpis(schema, numeric_stats)
    matched_cols: set[str] = {kpi["column"] for kpi in kpis}

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

    if not [kpi for kpi in kpis if kpi["kpi_type"] != "outcome_rate"]:
        kpis.extend(_fallback_kpis(schema, numeric_stats))

    # Sort by importance
    priority = {
        "outcome_rate": -1,
        "revenue": 0, "arr": 1, "mrr": 2, "profit": 3, "orders": 4,
        "customers": 5, "margin": 6, "conversion": 7, "growth": 8,
        "aov": 9, "asset_value": 10, "average": 11,
        "duration": 12, "retention": 13, "churn": 14, "cost": 15,
        "return": 16, "inventory": 17, "other": 18,
    }
    kpis.sort(key=lambda k: priority.get(k["kpi_type"], 9))
    return kpis[:10]


# Checked in order: the first vocabulary whose keywords appear as whole tokens
# in the column name wins. Average-style names (rating, score, rate, ...) are
# checked first: a "customer satisfaction rating" is a score, not a customer
# count, and only business metrics should be forecastable.
_KPI_TYPE_KEYWORDS: tuple[tuple[str, list[str]], ...] = (
    ("average", AVERAGE_METRIC_KEYWORDS),
    ("asset_value", ASSET_VALUE_KEYWORDS),
    ("arr", ARR_KEYWORDS),
    ("mrr", MRR_KEYWORDS),
    ("revenue", REVENUE_KEYWORDS),
    ("margin", MARGIN_KEYWORDS),
    ("profit", PROFIT_KEYWORDS),
    ("orders", ORDER_KEYWORDS),
    ("customers", CUSTOMER_KEYWORDS),
    ("conversion", CONVERSION_KEYWORDS),
    ("growth", GROWTH_KEYWORDS),
    ("aov", AOV_KEYWORDS),
    ("retention", RETENTION_KEYWORDS),
    ("churn", CHURN_KEYWORDS),
    ("cost", COST_KEYWORDS),
    ("return", RETURN_KEYWORDS),
    ("inventory", INVENTORY_KEYWORDS),
    ("duration", DURATION_KEYWORDS),
)

CURRENCY_KEYWORDS = [
    "revenue", "sales", "profit", "cost", "price", "amount", "income",
    "spend", "value", "valuation", "gmv", "mrr", "arr", "aov",
]

_AVERAGE_NAME_KEYWORDS = ["pct", "percent", "percentage", "rate", *AVERAGE_METRIC_KEYWORDS]


def _classify_column(col: str) -> str | None:
    for kpi_type, keywords in _KPI_TYPE_KEYWORDS:
        if contains_keyword(col, keywords):
            return kpi_type
    return None


def _is_currency(col: str) -> bool:
    return contains_keyword(col, CURRENCY_KEYWORDS)


def _uses_average(col: str, kpi_type: str) -> bool:
    return kpi_type in {
        "margin", "conversion", "growth", "retention", "churn", "return", "average"
    } or contains_keyword(col, _AVERAGE_NAME_KEYWORDS)


def uses_average_aggregation(column: str, kpi_type: str | None = None) -> bool:
    """Whether a column should be averaged rather than summed.

    The single source of truth for KPI tiles and for charts. They used separate
    keyword lists, so `total_profit` (or `mrr`, `arr`, `gmv`) was summed on its
    tile and averaged on its own chart — the same metric, two different numbers.
    A column with no recognised business meaning is averaged, matching what the
    KPI fallback already does with it.
    """
    resolved = kpi_type or _classify_column(column)
    if resolved is None:
        return True
    return _uses_average(column, resolved)


def _is_metric_role(col_info: dict[str, Any]) -> bool:
    role = col_info.get("analysis_role")
    return role in {None, "metric"}


def _is_non_kpi_numeric(col: str) -> bool:
    parts = set(col.split("_"))
    return (
        col == "year"
        or col.endswith("_year")
        or col == "id"
        or col.endswith("_id")
        or col.startswith("id_")
        or col.startswith("is_")
        or col.startswith("has_")
        or any(keyword in parts for keyword in NON_KPI_NUMERIC_KEYWORDS)
    )


def is_outcome_column(col: str) -> bool:
    parts = set(col.split("_"))
    return any(keyword in parts for keyword in OUTCOME_KEYWORDS)


def _outcome_rate_kpis(
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """Binary outcome columns (role "flag") are the headline of datasets like
    heart-disease or churn data — surface the share of positive records."""
    kpis = []
    for col_info in schema:
        if not col_info["is_numeric"] or col_info.get("analysis_role") != "flag":
            continue
        col = col_info["name"]
        col_lower = col.lower().replace(" ", "_")
        if not is_outcome_column(col_lower):
            continue
        mean = numeric_stats.get(col, {}).get("mean")
        if mean is None:
            continue
        kpis.append({
            "column": col,
            "kpi_type": "outcome_rate",
            "value": round(mean * 100, 1),
            "is_total": False,
            "is_percent": True,
            "is_currency": False,
            "mean": mean,
            "count": numeric_stats.get(col, {}).get("count", 0),
        })
    return kpis


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
        # No keyword matched, so we don't know the column is additive —
        # a raw SUM of e.g. blood pressures or 0/1 codes is meaningless.
        # The average is the only safe headline value for an unknown metric.
        value = stats.get("mean")
        if value is None:
            continue
        ranked.append({
            "column": col,
            "kpi_type": "other",
            "value": value,
            "is_total": False,
            "is_currency": _is_currency(col.lower().replace(" ", "_")),
            "mean": stats.get("mean"),
            "count": stats.get("count", 0),
            "score": _fallback_score(col_lower, stats),
            "fallback_reason": "Average of a numeric column with no recognized business meaning",
        })
    ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
    for item in ranked:
        item.pop("score", None)
    return ranked[:4]


def _fallback_score(col: str, stats: dict[str, Any]) -> float:
    score = 0.0
    if _uses_average(col, "other"):
        score += 35
    if any(keyword in col for keyword in DURATION_KEYWORDS):
        score += 12
    if _is_currency(col):
        score += 10
    non_null = float(stats.get("count") or 0)
    score += min(non_null / 1000, 5)
    return score
