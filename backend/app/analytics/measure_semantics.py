"""Conservative, domain-independent rules for measures and time fields."""

from __future__ import annotations

import re
from typing import Any

from app.analytics.text_matching import contains_keyword

VOLUME_KEYWORDS = (
    "streams", "plays", "views", "downloads", "clicks", "impressions", "visits",
    "sessions", "requests", "events", "shipments", "deliveries", "attendance",
)
NON_ADDITIVE_KEYWORDS = (
    "average", "avg", "mean", "median", "price", "rate", "ratio", "percent",
    "percentage", "pct", "score", "rating", "confidence", "duration", "speed",
    "margin", "rank", "position", "age", "height", "latitude", "longitude",
    "inventory", "stock", "balance", "cumulative", "lifetime",
    "growth", "change", "conversion", "retention", "churn", "yoy", "mom", "per",
)
FLOW_KEYWORDS = (
    "revenue", "sales", "income", "profit", "earnings", "amount", "cost",
    "expense", "spend", "orders", "transactions", "purchases", "bookings",
    "invoices", "quantity", "units_sold", *VOLUME_KEYWORDS,
)


def tokens(name: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", name.lower()))


def calendar_component(name: str, stats: dict[str, Any]) -> str | None:
    """Require both calendar vocabulary and plausible component bounds."""
    words = tokens(name)
    if words & {"per", "each", "total", "count", "average", "avg", *FLOW_KEYWORDS}:
        return None
    minimum, maximum = stats.get("min"), stats.get("max")
    if minimum is None or maximum is None:
        return None
    for component, upper in (("day", 31), ("month", 12), ("quarter", 4)):
        if component in words and 1 <= minimum <= maximum <= upper:
            return component
    return None


def is_additive_flow(name: str) -> bool:
    """Only affirmative flow/count vocabulary qualifies for a SUM forecast.

    Unknown numeric attributes are still describable, but their sum is not a
    defensible forecast target. Calendar density alone cannot establish this.
    """
    words = tokens(name)
    if words & {"id", "year", "month", "day", "quarter", "flag"}:
        return False
    if "unit" in words:
        return False
    return (
        not contains_keyword(name, NON_ADDITIVE_KEYWORDS)
        and contains_keyword(name, FLOW_KEYWORDS)
    )


def is_observation_date(name: str) -> bool:
    # Catalogue/lifecycle dates group entities into cohorts, not period flows.
    words = tokens(name)
    # Week/month/period start and end are ordinary reporting boundaries.
    if words & {"period", "week", "month", "quarter", "year"}:
        words -= {"start", "end"}
    return not words & {
        "first", "last", "birth", "born", "death", "released", "release",
        "published", "publication", "created", "updated", "start", "end",
        "started", "ended", "expiry", "expiration", "deadline", "due",
        "creation", "snapshot", "asof",
    }
