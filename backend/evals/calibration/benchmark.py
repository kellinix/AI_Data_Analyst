"""
Seeded synthetic datasets with planted ground truth.

Every dataset comes from a known generating process, so each recommendation
the pipeline makes about it can be checked:

- a flagged standout record was either a planted anomaly or ordinary variation
  (heavy-noise datasets produce z >= 3 records naturally);
- a flagged gap was either a real defect (a broken tracking feed) or an
  optional-by-design column that is blank most of the time;
- a forecast move either happened or didn't in a held-back month the pipeline
  never sees.

The scenario mix — how often each kind of truth occurs — is a choice made in
`draw_scenarios`, and hit rates measured on this benchmark depend on it. The
report splits results by scenario so they can be reweighted.
"""

from __future__ import annotations

import csv
import itertools
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

BENCHMARK_VERSION = "2026-09-11.1"
DEFAULT_SEED = 20260911


@dataclass(frozen=True)
class Domain:
    name: str
    description: str
    dims: dict[str, tuple[str, ...]]
    revenue: str
    volume: str
    customers: str
    base_volume: float
    unit_price: tuple[float, float]
    customers_per_unit: float
    optional_column: str
    optional_story: str


DOMAINS: tuple[Domain, ...] = (
    Domain(
        name="outdoor_retail",
        description="Sales for an outdoor-apparel retailer by region and product category.",
        dims={
            "region": ("North America", "Europe", "Asia Pacific"),
            "category": ("Apparel", "Footwear", "Camping"),
        },
        revenue="revenue",
        volume="units_sold",
        customers="new_customers",
        base_volume=400,
        unit_price=(35, 120),
        customers_per_unit=0.3,
        optional_column="promo_discount",
        optional_story=(
            "promo_discount is only recorded for rows where a promotion ran; a blank "
            "means no promotion that period, not missing data."
        ),
    ),
    Domain(
        name="online_marketplace",
        description="Marketplace activity by sales channel and country.",
        dims={
            "channel": ("Web", "iOS", "Android"),
            "country": ("United Kingdom", "Germany", "France"),
        },
        revenue="gmv",
        volume="orders",
        customers="visitors",
        base_volume=1500,
        unit_price=(20, 80),
        customers_per_unit=18.0,
        optional_column="refund_total",
        optional_story=(
            "refund_total is only filled when a refund was issued in that period; a "
            "blank means no refunds, not missing data."
        ),
    ),
    Domain(
        name="b2b_software",
        description="B2B software sales by customer segment and region.",
        dims={
            "segment": ("SMB", "Mid-Market", "Enterprise"),
            "region": ("Americas", "EMEA", "APAC"),
        },
        revenue="sales",
        volume="deals",
        customers="leads",
        base_volume=60,
        unit_price=(2000, 15000),
        customers_per_unit=6.0,
        optional_column="partner_commission",
        optional_story=(
            "partner_commission is only filled for deals sourced through a reseller "
            "partner; a blank means a direct deal, not missing data."
        ),
    ),
    Domain(
        name="hotel_group",
        description="Hotel group performance by property and room type.",
        dims={
            "property": ("Harbour View", "City Centre", "Airport"),
            "room_type": ("Standard", "Deluxe", "Suite"),
        },
        revenue="revenue",
        volume="bookings",
        customers="customers",
        base_volume=300,
        unit_price=(90, 400),
        customers_per_unit=1.6,
        optional_column="upgrade_fee",
        optional_story=(
            "upgrade_fee is only charged when a guest upgraded their room; a blank "
            "means no upgrade, not missing data."
        ),
    ),
)


@dataclass(frozen=True)
class Scenario:
    dataset_id: str
    seed: int
    domain: Domain
    grain: str  # "weekly" | "monthly"
    months: int
    start: date
    growth: float  # true monthly growth rate
    seasonality: float  # Nov-Dec uplift (and a smaller Jan-Feb dip)
    noise: float  # lognormal sigma on volume
    plant_anomaly: bool
    tracking_outage: bool
    optional_sparse: bool

    @property
    def date_column(self) -> str:
        return "week_start_date" if self.grain == "weekly" else "month_start_date"

    def describe(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "domain": self.domain.name,
            "grain": self.grain,
            "months": self.months,
            "start": self.start.isoformat(),
            "growth": self.growth,
            "seasonality": self.seasonality,
            "noise": self.noise,
            "plant_anomaly": self.plant_anomaly,
            "tracking_outage": self.tracking_outage,
            "optional_sparse": self.optional_sparse,
        }


def draw_scenarios(count: int, seed: int = DEFAULT_SEED) -> list[Scenario]:
    """A balanced, reproducible mix of scenarios.

    Half the datasets get a planted anomaly, a third a tracking outage, half an
    optional-by-design sparse column, assigned by shuffled quotas so no flag
    lines up with a domain or grain.
    """
    rng = np.random.default_rng(seed)

    def quota(fraction: float) -> list[bool]:
        flags = [index < round(count * fraction) for index in range(count)]
        rng.shuffle(flags)
        return flags

    anomalies, outages, sparse = quota(0.5), quota(1 / 3), quota(0.5)
    scenarios = []
    for index in range(count):
        domain = DOMAINS[index % len(DOMAINS)]
        grain = "weekly" if (index // len(DOMAINS)) % 2 == 0 else "monthly"
        scenarios.append(
            Scenario(
                dataset_id=f"{index:03d}_{domain.name}_{grain}",
                seed=seed * 1000 + index,
                domain=domain,
                grain=grain,
                months=int(rng.integers(12, 25)),
                start=date(int(rng.integers(2022, 2025)), int(rng.integers(1, 13)), 1),
                growth=float(rng.choice([-0.08, -0.04, 0.0, 0.03, 0.08])),
                seasonality=float(rng.choice([0.0, 0.25])),
                noise=float(rng.choice([0.08, 0.3])),
                plant_anomaly=anomalies[index],
                tracking_outage=outages[index],
                optional_sparse=sparse[index],
            )
        )
    return scenarios


def write_dataset(scenario: Scenario, directory: Path) -> tuple[Path, dict[str, Any]]:
    """Write the observed CSV and return (path, ground truth)."""
    observed, holdout, planted = _generate_rows(scenario)
    domain = scenario.domain
    columns = [
        scenario.date_column,
        *domain.dims,
        domain.revenue,
        domain.volume,
        domain.customers,
        *([domain.optional_column] if scenario.optional_sparse else []),
    ]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{scenario.dataset_id}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in observed:
            writer.writerow({key: ("" if row.get(key) is None else row[key]) for key in columns})
    return path, _ground_truth(scenario, observed, holdout, planted)


# ── Generation ──────────────────────────────────────────────────────────────


def _add_months(value: date, months: int) -> date:
    year, month = divmod(value.month - 1 + months, 12)
    return date(value.year + year, month + 1, 1)


def _month_index(value: date, start: date) -> int:
    return (value.year - start.year) * 12 + value.month - start.month


def _periods(scenario: Scenario) -> list[date]:
    """Period start dates covering the observed months plus one holdout month."""
    if scenario.grain == "monthly":
        return [_add_months(scenario.start, offset) for offset in range(scenario.months + 1)]
    current = scenario.start + timedelta(days=(7 - scenario.start.weekday()) % 7)
    periods = []
    while _month_index(current, scenario.start) <= scenario.months:
        periods.append(current)
        current += timedelta(days=7)
    return periods


def _seasonal_factor(month: int, strength: float) -> float:
    if month in (11, 12):
        return 1 + strength
    if month in (1, 2):
        return 1 - strength * 0.3
    return 1.0


def _generate_rows(
    scenario: Scenario,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    rng = np.random.default_rng(scenario.seed)
    domain = scenario.domain
    combos = list(itertools.product(*domain.dims.values()))
    scale = {combo: float(rng.lognormal(0, 0.35)) for combo in combos}
    price = {combo: float(rng.uniform(*domain.unit_price)) for combo in combos}
    per_period = 1.0 if scenario.grain == "monthly" else 7 / 30.44

    rows: list[dict[str, Any]] = []
    for period in _periods(scenario):
        month = _month_index(period, scenario.start)
        elapsed = month + (period.day - 1) / 30.44
        trend = (1 + scenario.growth) ** elapsed
        season = _seasonal_factor(period.month, scenario.seasonality)
        for combo in combos:
            level = domain.base_volume * scale[combo] * trend * season * per_period
            volume = max(0, round(level * float(rng.lognormal(0, scenario.noise))))
            revenue = round(volume * price[combo] * float(rng.lognormal(0, 0.05)), 2)
            customers = round(volume * domain.customers_per_unit * float(rng.lognormal(0, 0.1)))
            optional_draw, optional_share = float(rng.random()), float(rng.uniform(0.05, 0.15))
            row: dict[str, Any] = {
                "_month": month,
                scenario.date_column: period.isoformat(),
                **dict(zip(domain.dims, combo, strict=True)),
                domain.revenue: revenue,
                domain.volume: volume,
                domain.customers: customers,
            }
            if scenario.optional_sparse:
                row[domain.optional_column] = (
                    round(revenue * optional_share, 2) if optional_draw < 0.2 else None
                )
            rows.append(row)

    if scenario.tracking_outage:
        cutoff = max(1, scenario.months // 4)
        for row in rows:
            if row["_month"] >= cutoff:
                row[domain.customers] = None

    observed = [row for row in rows if row["_month"] < scenario.months]
    holdout = [row for row in rows if row["_month"] == scenario.months]
    planted = _plant_anomaly(scenario, observed, rng) if scenario.plant_anomaly else None
    return observed, holdout, planted


def _plant_anomaly(
    scenario: Scenario, observed: list[dict[str, Any]], rng: np.random.Generator
) -> dict[str, Any]:
    """Scale one record until it is unambiguously the most extreme revenue value."""
    domain = scenario.domain
    candidates = [
        index
        for index, row in enumerate(observed)
        if 1 <= row["_month"] <= scenario.months - 3 and row[domain.revenue] > 0
    ]
    index = int(rng.choice(candidates))
    row = observed[index]
    affected = [domain.revenue, domain.volume] + (
        [domain.customers] if row[domain.customers] is not None else []
    )
    original = {column: row[column] for column in affected}
    kind = str(rng.choice(["spike", "collapse"]))
    factor = float(rng.uniform(4, 6)) if kind == "spike" else float(rng.uniform(0.05, 0.12))

    for _ in range(40):
        for column in affected:
            scaled = original[column] * factor
            row[column] = round(scaled, 2) if column == domain.revenue else round(scaled)
        values = np.array([other[domain.revenue] for other in observed], dtype=float)
        z_scores = np.abs(values - values.mean()) / values.std(ddof=1)
        if z_scores[index] >= 3.5 and int(np.argmax(z_scores)) == index:
            break
        if kind == "collapse":
            kind, factor = "spike", float(rng.uniform(4, 6))
        else:
            factor *= 1.3
    else:  # pragma: no cover - guarded by the generator's own tests
        raise RuntimeError(f"Could not plant a dominant anomaly in {scenario.dataset_id}")

    return {
        "row_index": index,
        "date": row[scenario.date_column],
        "month": row[scenario.date_column][:7],
        "dimensions": {dim: row[dim] for dim in domain.dims},
        "columns": affected,
        "kind": kind,
        "factor": round(factor, 3),
        "revenue_z_score": round(float(z_scores[index]), 2),
        "story": (
            f"A genuine one-off event: {'a bulk order' if kind == 'spike' else 'a checkout outage'} "
            f"made this record's {', '.join(affected)} about {factor:.2f}x normal. "
            "It is worth investigating."
        ),
    }


# ── Ground truth ────────────────────────────────────────────────────────────


def _ground_truth(
    scenario: Scenario,
    observed: list[dict[str, Any]],
    holdout: list[dict[str, Any]],
    planted: dict[str, Any] | None,
) -> dict[str, Any]:
    domain = scenario.domain
    metrics = [domain.revenue, domain.volume, domain.customers]
    date_column = scenario.date_column

    def total(rows: list[dict[str, Any]], column: str) -> float | None:
        values = [row[column] for row in rows if row.get(column) is not None]
        return round(float(sum(values)), 2) if values else None

    months = sorted({row[date_column][:7] for row in observed})
    last_month_rows = [row for row in observed if row[date_column][:7] == months[-1]]
    monthly_totals = {
        metric: {
            month: total([row for row in observed if row[date_column][:7] == month], metric)
            for month in months
        }
        for metric in metrics
    }
    holdout_totals = {metric: total(holdout, metric) for metric in metrics}
    last_totals = {metric: total(last_month_rows, metric) for metric in metrics}
    change = {
        metric: (
            round((holdout_totals[metric] - last_totals[metric]) / last_totals[metric] * 100, 2)
            if holdout_totals[metric] is not None and last_totals[metric]
            else None
        )
        for metric in metrics
    }
    dimension_totals = {
        metric: {
            dim: {value: total([row for row in observed if row[dim] == value], metric) for value in values}
            for dim, values in domain.dims.items()
        }
        for metric in (domain.revenue, domain.volume)
    }

    columns = {
        date_column: f"Start date of each {'week' if scenario.grain == 'weekly' else 'month'}.",
        **{dim: f"Dimension: {', '.join(values)}." for dim, values in domain.dims.items()},
        domain.revenue: "Revenue for the row, in the business's currency.",
        domain.volume: f"Count of {domain.volume.replace('_', ' ')} for the row.",
        domain.customers: f"Count of {domain.customers.replace('_', ' ')} for the row.",
    }
    if scenario.optional_sparse:
        columns[domain.optional_column] = domain.optional_story

    defect_story = None
    if scenario.tracking_outage:
        cutoff_month = _add_months(scenario.start, max(1, scenario.months // 4)).isoformat()[:7]
        defect_story = (
            f"The tracking feed for {domain.customers} broke in {cutoff_month}; every "
            f"{domain.customers} value from then on is blank. This is a real data defect "
            f"and {domain.customers} totals after {cutoff_month} are not trustworthy."
        )

    return {
        "benchmark_version": BENCHMARK_VERSION,
        "dataset_id": scenario.dataset_id,
        "scenario": scenario.describe(),
        "domain_description": domain.description,
        "date_column": date_column,
        "dimensions": list(domain.dims),
        "metrics": metrics,
        "observed_period": [months[0], months[-1]],
        "row_count": len(observed),
        "columns": columns,
        "generating_process": {
            "true_monthly_growth_percent": round(scenario.growth * 100, 1),
            "seasonality": (
                f"Nov-Dec demand about {scenario.seasonality:.0%} above baseline, Jan-Feb slightly below."
                if scenario.seasonality
                else "No seasonality."
            ),
            "noise": (
                "High: individual records vary a lot, and records 3+ standard deviations from "
                "the mean occur naturally. Such records are ordinary variation, not errors or events."
                if scenario.noise >= 0.2
                else "Low: records vary modestly around the trend."
            ),
        },
        "planted_anomaly": planted,
        "no_planted_anomaly_note": (
            None
            if planted
            else "No genuine anomaly exists. Any standout record is ordinary random variation."
        ),
        "defect_columns": [domain.customers] if scenario.tracking_outage else [],
        "defect_story": defect_story,
        "by_design_sparse_columns": [domain.optional_column] if scenario.optional_sparse else [],
        "missing_percent_by_column": {
            column: round(100 * sum(row.get(column) is None for row in observed) / len(observed), 1)
            for column in columns
            if any(row.get(column) is None for row in observed)
        },
        "observed_monthly_totals": monthly_totals,
        "dimension_totals": dimension_totals,
        "correlations": _correlations(observed, metrics),
        "holdout": {
            "month": holdout[0][date_column][:7] if holdout else None,
            "totals": holdout_totals,
            "last_observed_month_totals": last_totals,
            "change_percent_vs_last_observed_month": change,
        },
    }


def _correlations(rows: list[dict[str, Any]], metrics: list[str]) -> dict[str, float]:
    result = {}
    for left, right in itertools.combinations(metrics, 2):
        pairs = [
            (row[left], row[right])
            for row in rows
            if row.get(left) is not None and row.get(right) is not None
        ]
        if len(pairs) > 2:
            matrix = np.corrcoef(np.array(pairs, dtype=float).T)
            result[f"{left}~{right}"] = round(float(matrix[0, 1]), 3)
    return result
