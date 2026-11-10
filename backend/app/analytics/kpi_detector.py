"""
KPI Detector — Identifies business KPIs from column names and statistics.
Never asks the user. Automatically infers what matters.
"""

from __future__ import annotations

from typing import Any

from app.analytics.measure_grain import analytical_numeric_statistics, analytical_schema
from app.analytics.measure_semantics import (
    VOLUME_KEYWORDS,
    calendar_component,
    is_additive_flow,
    is_power_reading,
    is_rate_or_average,
)
from app.analytics.percentage_scale import SCALE_WARNING, ambiguous_percentage
from app.analytics.text_matching import contains_keyword

# Keyword maps for KPI detection
REVENUE_KEYWORDS = ["revenue", "sales", "income", "turnover", "gross", "net_revenue", "total_sales", "amount", "money", "price", "value", "gmv"]
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
    "cgpa", "gpa", "chance", "ratio", "speed", "impact", "satisfaction", "nps",
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
    "success", "disease", "readmitted", "defaulted", "hired",
]


def detect_kpis(
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Return a list of detected KPIs with their values and metadata.
    """
    numeric_stats = analytical_numeric_statistics(schema, numeric_stats)
    schema = analytical_schema(schema)
    from app.analytics.survey_context import survey_fields
    if survey_fields(schema):
        return []
    kpis = _outcome_rate_kpis(schema, numeric_stats)
    semantic_types = {column["name"]: column.get("semantic_type") for column in schema}
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
        if calendar_component(col, stats):
            continue
        total = stats.get("total")
        mean = stats.get("mean")
        count = stats.get("count", 0)

        if total is None and mean is None:
            continue

        kpi_type = _classify_column(col_lower)
        if kpi_type and col not in matched_cols:
            matched_cols.add(col)
            power_reading = is_power_reading(col, col_info)
            use_mean = uses_average_aggregation(col_lower, kpi_type, field=col_info)
            # A percentage averaged over records lets a tiny record outvote a
            # huge one; the statistics layer weights it by the money it
            # applies to when it can work out which column that is.
            weighted = stats.get("weighted_mean") if use_mean else None
            if use_mean and weighted is None and mean is None:
                continue
            if weighted is not None:
                value = weighted
            elif use_mean and mean is not None:
                value = mean
            else:
                value = total if total is not None else mean
            kpis.append({
                "column": col,
                "kpi_type": kpi_type,
                "value": value,
                "is_total": not use_mean and total is not None,
                "is_currency": _is_currency(col_lower) and not power_reading,
                "is_percent": "%" in col or contains_keyword(col_lower, ["pct", "percent", "percentage"]),
                "display_multiplier": 1,
                "mean": mean,
                "count": count,
                "weighted_by": stats.get("weight_column") if weighted is not None else None,
            })

    # A recognised score must not suppress every other numeric measure.
    # Fill available slots with safely averaged, non-calendar metrics.
    kpis.extend(_fallback_kpis([col for col in schema if col["name"] not in matched_cols], numeric_stats))

    # Sort by importance
    priority = {
        "outcome_rate": -1,
        "revenue": 0, "arr": 1, "mrr": 2, "profit": 3, "orders": 4,
        "volume": 4.5, "customers": 5, "margin": 6, "conversion": 7, "growth": 8,
        "aov": 9, "asset_value": 10, "average": 11,
        "duration": 12, "retention": 13, "churn": 14, "cost": 15,
        "return": 16, "inventory": 17, "other": 18,
    }
    kpis.sort(key=lambda k: (
        19 if contains_keyword(k["column"], ["confidence", "similarity", "match_score"])
        else -3 if k["column"] == "chance_of_admit"
        else -2 if k["column"] == "cgpa"
        else 0.5 if k["column"] in {"total", "net_total", "grand_total"}
        else priority.get(k["kpi_type"], 9)
    ))
    for kpi in kpis:
        if kpi.get("is_percent") or semantic_types.get(kpi["column"]) == "percentage":
            kpi["is_currency"] = False
        if kpi["column"] == "chance_of_admit":
            kpi["value"] = round(kpi["value"], 12) * 100
            kpi["is_percent"] = True
            kpi["display_multiplier"] = 100
        stats = numeric_stats.get(kpi["column"], {})
        if ambiguous_percentage(kpi["column"], stats):
            kpi.update({"is_percent": False, "is_currency": False, "display_multiplier": 1,
                        "percentage_scale": "unconfirmed", "display_warning": SCALE_WARNING})
    return kpis[:10]


# Checked in order: the first vocabulary whose keywords appear as whole tokens
# in the column name wins. Average-style names (rating, score, rate, ...) are
# checked first: a "customer satisfaction rating" is a score, not a customer
# count, and only business metrics should be forecastable.
_KPI_TYPE_KEYWORDS: tuple[tuple[str, list[str]], ...] = (
    ("average", AVERAGE_METRIC_KEYWORDS),
    ("volume", list(VOLUME_KEYWORDS)),
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
    "spend", "value", "valuation", "gmv", "mrr", "arr", "aov", "money",
]

_AVERAGE_NAME_KEYWORDS = ["pct", "percent", "percentage", "rate", "price", "per", *AVERAGE_METRIC_KEYWORDS]


def _classify_column(col: str) -> str | None:
    if col == "kwh_consumed":
        return "orders"
    if col == "total_cos_used":
        # Each row is an organisation's count for a reported source sheet;
        # averaging those counts hides the overall number of certificates.
        return "orders"
    # A row-level Total is additive, but its unit is unknown without context.
    if col in {"total", "net_total", "grand_total"}:
        return "other"
    if contains_keyword(col, ["price"]):
        return "average"
    for kpi_type, keywords in _KPI_TYPE_KEYWORDS:
        if kpi_type == "volume" and not is_additive_flow(col):
            continue
        if contains_keyword(col, keywords):
            return kpi_type
    return None


def _is_currency(col: str) -> bool:
    return contains_keyword(col, CURRENCY_KEYWORDS)


def _uses_average(col: str, kpi_type: str) -> bool:
    return is_power_reading(col) or kpi_type in {
        "margin", "conversion", "growth", "retention", "churn", "return", "average", "duration"
    } or contains_keyword(col, _AVERAGE_NAME_KEYWORDS)


def uses_average_aggregation(column: str, kpi_type: str | None = None, *, field: dict[str, Any] | None = None) -> bool:
    """Whether a column should be averaged rather than summed.

    The single source of truth for KPI tiles and for charts. They used separate
    keyword lists, so `total_profit` (or `mrr`, `arr`, `gmv`) was summed on its
    tile and averaged on its own chart — the same metric, two different numbers.
    A column with no recognised business meaning is averaged, matching what the
    KPI fallback already does with it.
    """
    resolved = kpi_type or _classify_column(column)
    if is_rate_or_average(column, field) or is_power_reading(column, field):
        return True
    if (field or {}).get("semantic_type") == "count" and not _uses_average(column, resolved or "other"):
        return False
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
        if calendar_component(col, stats):
            continue
        # Original-header semantics can establish a recorded count even when
        # its cleaned SQL name no longer contains separated business words.
        use_mean = uses_average_aggregation(col_lower, field=col_info)
        weighted = stats.get("weighted_mean") if use_mean else None
        value = (weighted if weighted is not None else stats.get("mean")) if use_mean else stats.get("total")
        if value is None:
            continue
        ranked.append({
            "column": col,
            "kpi_type": "other",
            "value": value,
            "is_total": not use_mean,
            "is_currency": _is_currency(col.lower().replace(" ", "_")),
            "mean": stats.get("mean"),
            "count": stats.get("count", 0),
            "weighted_by": stats.get("weight_column") if weighted is not None else None,
            "score": _fallback_score(col_lower, stats),
            "fallback_reason": "Average of a numeric column with no recognized business meaning" if use_mean else "Total of a recorded count measure",
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
