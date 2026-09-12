"""
Calibration metrics over scored recommendations.

A recommendation is scored as a (confidence shown, correct?) pair. For a
well-calibrated source, recommendations shown at 0.8 are correct about 80% of
the time. Everything here is plain arithmetic so it can be unit-tested and
re-run on committed results without network access.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Scored:
    dataset_id: str
    source: str
    confidence: float
    correct: bool


def brier_score(items: Sequence[Scored]) -> float | None:
    """Mean squared gap between confidence and outcome (0 is perfect)."""
    if not items:
        return None
    return sum((item.confidence - float(item.correct)) ** 2 for item in items) / len(items)


def reliability_table(items: Sequence[Scored], bins: int = 5) -> list[dict]:
    """Equal-width confidence bins with the observed hit rate in each."""
    rows = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        members = [
            item
            for item in items
            if lower <= item.confidence < upper or (index == bins - 1 and item.confidence == 1.0)
        ]
        rows.append(
            {
                "bin": f"{lower:.1f}-{upper:.1f}",
                "n": len(members),
                "mean_confidence": _mean(item.confidence for item in members),
                "hit_rate": _mean(float(item.correct) for item in members),
            }
        )
    return rows


def expected_calibration_error(items: Sequence[Scored], bins: int = 5) -> float | None:
    """Sample-weighted mean |confidence - hit rate| across reliability bins."""
    if not items:
        return None
    total = 0.0
    for row in reliability_table(items, bins):
        if row["n"]:
            total += row["n"] * abs(row["mean_confidence"] - row["hit_rate"])
    return total / len(items)


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial rate (well-behaved at small n)."""
    if n == 0:
        return (0.0, 1.0)
    rate = hits / n
    denominator = 1 + z**2 / n
    centre = (rate + z**2 / (2 * n)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / n + z**2 / (4 * n**2)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def smoothed_rate(hits: int, n: int) -> float:
    """Hit rate under a uniform Beta(1, 1) prior — never exactly 0 or 1."""
    return (hits + 1) / (n + 2)


def leave_one_dataset_out_brier(items: Sequence[Scored]) -> float | None:
    """Brier score of the recalibrated confidence, estimated honestly.

    Each recommendation is scored against the smoothed hit rate of its source
    measured on every *other* dataset, so the recalibrated number is never
    judged on the data it was fitted to.
    """
    if not items:
        return None
    by_source: dict[str, list[Scored]] = defaultdict(list)
    for item in items:
        by_source[item.source].append(item)

    squared_errors = []
    for item in items:
        others = [
            other for other in by_source[item.source] if other.dataset_id != item.dataset_id
        ]
        estimate = smoothed_rate(sum(other.correct for other in others), len(others))
        squared_errors.append((estimate - float(item.correct)) ** 2)
    return sum(squared_errors) / len(squared_errors)


def summarize_by_source(items: Iterable[Scored]) -> dict[str, dict]:
    """Per-source calibration summary, including the recalibrated confidence."""
    by_source: dict[str, list[Scored]] = defaultdict(list)
    for item in items:
        by_source[item.source].append(item)

    summary = {}
    for source, members in sorted(by_source.items()):
        hits = sum(item.correct for item in members)
        low, high = wilson_interval(hits, len(members))
        summary[source] = {
            "n": len(members),
            "hits": hits,
            "hit_rate": _round(hits / len(members)),
            "hit_rate_95ci": [_round(low), _round(high)],
            "datasets": len({item.dataset_id for item in members}),
            "mean_confidence_shown": _round(_mean(item.confidence for item in members)),
            "brier_shown": _round(brier_score(members)),
            "brier_recalibrated_loo": _round(leave_one_dataset_out_brier(members)),
            "recalibrated_confidence": _round(smoothed_rate(hits, len(members))),
        }
    return summary


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)
