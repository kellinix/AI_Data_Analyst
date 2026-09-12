"""
Shared shape checks for monthly series.

Whether a set of month starts is dense enough to treat as a time series at all.
A project portfolio's start dates spanning 1997-2024 produce 41 monthly points
across 27 years: forecasting read that as a trend and projected "next month"
from it, and monthly anomaly detection z-scored those same sparse buckets.
Both now ask this module first, so they can't drift apart.
"""

from __future__ import annotations

from typing import Any, Protocol


class _HasYearMonth(Protocol):
    year: int
    month: int


# Share of the months between the first and last observation that carry data.
MIN_MONTHLY_DENSITY = 0.6


def monthly_density(periods: list[Any]) -> float:
    """Fraction of the months spanned that actually have an observation."""
    if not periods:
        return 0.0
    span = span_months(periods[0], periods[-1])
    return len(periods) / span if span > 0 else 0.0


def span_months(first: _HasYearMonth, last: _HasYearMonth) -> int:
    return (last.year - first.year) * 12 + (last.month - first.month) + 1


def is_dense_monthly_series(periods: list[Any]) -> bool:
    """True when the periods form a series rather than a scatter of dates."""
    return monthly_density(periods) >= MIN_MONTHLY_DENSITY
