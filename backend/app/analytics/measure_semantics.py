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


def _declared_unit(field: dict[str, Any] | None) -> str:
    metadata = field or {}
    supplied = (metadata.get("data_definition") or {}).get("unit")
    return str(supplied or metadata.get("unit") or metadata.get("display_unit") or "").strip().lower()


def _provided_numeric_label(field: dict[str, Any] | None) -> str:
    metadata = field or {}
    if not metadata.get("is_numeric") or metadata.get("analysis_role") not in {None, "metric", "attribute"}:
        return ""
    label = str((metadata.get("data_definition") or {}).get("label") or "")
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", label)


def is_power_reading(name: str, field: dict[str, Any] | None = None) -> bool:
    """Power samples cannot be added into energy without known time intervals."""
    words = tokens(re.sub(r"([a-z])([A-Z])", r"\1_\2", f"{name} {_provided_numeric_label(field)}"))
    unit = _declared_unit(field)
    power_units = {"w", "kw", "mw", "watt", "watts", "kilowatt", "kilowatts", "megawatt", "megawatts"}
    if unit in power_units:
        return True
    # A kilowatt-hour is energy. The word kilowatt alone is power.
    if not words & {"hour", "hours", "hr", "hrs", "h"} and words & (power_units - {"w"}):
        return True
    # W alone can also mean wins, width or a code. Require power vocabulary.
    return "w" in words and bool(words & {
        "power", "load", "demand", "electric", "electricity", "consumption", "output", "input",
    })


def is_rate_or_average(name: str, field: dict[str, Any] | None = None) -> bool:
    """Rate/average fields need a per-entry average instead of a raw sum."""
    supplied_label = _provided_numeric_label(field)
    return bool(
        (field or {}).get("semantic_type") in {"percentage", "average_metric"}
        or _declared_unit(field) in {"%", "percent", "percentage", "pct", "per cent"}
        or name.lower() in {"cgpa", "gpa"}
        or supplied_label.strip().lower() in {"cgpa", "gpa"}
        or "%" in supplied_label
        or contains_keyword(supplied_label, ("average", "avg", "mean", "median", "percentage", "percent", "pct", "rate", "ratio"))
        or re.search(r"(?:^|_)(?:pct|percent|percentage|rate)(?:_|$)|%", name, re.I)
    )


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


def is_observation_date(
    name: str, field: dict[str, Any] | None = None, *, include_snapshot: bool = False,
) -> bool:
    # Catalogue/lifecycle dates group entities into cohorts, not period flows.
    original = str(((field or {}).get("measure_grain") or {}).get("source_column") or "")
    words = tokens(re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", f"{name} {original}"))
    compact = re.sub(r"[^a-z]", "", name.lower())
    if compact in {"dob", "dateofbirth", "birthdate", "debut"} or re.search(r"(?:open|opened|opening)date$", compact):
        return False
    # Week/month/period start and end are ordinary reporting boundaries.
    if words & {"period", "week", "month", "quarter", "year"}:
        words -= {"start", "end"}
    if include_snapshot:
        # A snapshot date can establish recency without qualifying a sequence
        # of stock snapshots for additive flow forecasting.
        words -= {"snapshot", "asof"}
    return not words & {
        "first", "last", "birth", "born", "death", "released", "release",
        "published", "publication", "created", "updated", "start", "end",
        "started", "ended", "expiry", "expiration", "deadline", "due",
        "creation", "snapshot", "asof",
        "open", "opened", "opening", "debut", "dob",
    }
