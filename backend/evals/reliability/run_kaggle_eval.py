"""Compare public Kaggle CSVs with Zephyr's real cleaning and analysis path.

Download the CC0 ihelon/coffee-sales and Apache-2.0
pimmadachirawat/supermarket-sales datasets separately. Source files stay out
of Git. Run from backend with explicit paths, for example::

    python -m evals.reliability.run_kaggle_eval --coffee ../tmp/kaggle/coffee/index_1.csv \
        --supermarket "../tmp/kaggle/supermarket/Supermarket Sales Data.csv"

AI is disabled so this gate tests measured results, not generated prose.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from evals.calibration.run_eval import _bootstrap_env, _OfflineAIService

CASES = {
    "coffee": {"measure": "money", "group": "cash_type"},
    "supermarket": {"measure": "Total", "group": "Branch"},
}


def source_facts(path: Path, measure: str, group: str) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    totals: dict[str, Decimal] = {}
    counts: Counter[str] = Counter()
    missing = 0
    total = Decimal(0)
    for row in rows:
        value = (row.get(measure) or "").strip()
        key = (row.get(group) or "").strip()
        counts[key] += 1
        if not value:
            missing += 1
            continue
        amount = Decimal(value.replace(",", ""))
        total += amount
        totals[key] = totals.get(key, Decimal(0)) + amount
    return {
        "rows": len(rows), "measure": measure, "group": group,
        "total": str(total), "missing_measure": missing,
        "group_counts": dict(counts),
        "group_totals": {key: str(value) for key, value in totals.items()},
    }


async def run_case(name: str, path: Path, workdir: Path, *, with_ai: bool) -> dict:
    print(f"{name}: loading source", file=sys.stderr, flush=True)
    import polars as pl

    from app.api.v1.endpoints.analyses import _cleaning_options
    from app.analytics.record_context import record_context
    from app.services.analysis_engine import compute_analysis
    from app.services.file_processor import FileProcessor

    config = CASES[name]
    source = source_facts(path, **config)
    target = workdir / f"{name}.cleaned.parquet"
    processor = FileProcessor()
    print(f"{name}: cleaning {source['rows']} rows", file=sys.stderr, flush=True)
    profile = await processor.clean_file(
        str(path), ".csv", str(target), str(target.with_suffix(".csv")),
        _cleaning_options({"mode": "clean"}),
    )
    frame = pl.read_parquet(target)
    print(f"{name}: analysing {frame.height} rows", file=sys.stderr, flush=True)
    if with_ai:
        from app.services.ai_service import AIService

        ai_service = AIService()
    else:
        ai_service = _OfflineAIService()
    computed = await compute_analysis(
        file_processor=processor, ai_service=ai_service,
        storage_path=str(target), file_name=path.name, analysis_id=f"kaggle-{name}",
        upload_context={"cleaning": {"enabled": True, "report": profile["cleaning_report"]}},
    )
    print(f"{name}: comparing results", file=sys.stderr, flush=True)
    measure_key = config["measure"].lower().replace(" ", "_")
    stats = computed["statistics"]["numeric_stats"].get(measure_key)
    actual_total = Decimal(str(stats["total"])) if stats and stats.get("total") is not None else None
    expected_total = Decimal(source["total"])
    failures = []
    if computed["row_count"] != source["rows"] or frame.height != source["rows"]:
        failures.append("Source rows changed during cleaning or analysis")
    if actual_total is None or abs(actual_total - expected_total) > Decimal("0.01"):
        failures.append(f"{config['measure']} total differs from source")
    if measure_key in frame.columns and frame[measure_key].null_count() != source["missing_measure"]:
        failures.append(f"{config['measure']} blanks changed during cleaning")
    group_key = config["group"].lower().replace(" ", "_")
    group_chart = next(
        (chart for chart in computed["charts"] if chart.get("type") == "bar"
         and chart.get("xAxis") == measure_key and chart.get("yAxis") == group_key),
        None,
    )
    displayed_totals: dict[str, Decimal] = {}
    if group_chart is None:
        failures.append(f"No {config['measure']} by {config['group']} chart")
    else:
        option = group_chart.get("echarts_option") or {}
        labels = (option.get("yAxis") or {}).get("data") or []
        values = ((option.get("series") or [{}])[0]).get("data") or []
        displayed_totals = {str(label): Decimal(str(value)) for label, value in zip(labels, values, strict=True)}
        expected_groups = {key: Decimal(value) for key, value in source["group_totals"].items()}
        if displayed_totals.keys() != expected_groups.keys() or any(
            abs(displayed_totals.get(key, Decimal(0)) - expected) > Decimal("0.01")
            for key, expected in expected_groups.items()
        ):
            failures.append(f"{config['measure']} by {config['group']} chart differs from source")
    headline = next((kpi for kpi in computed["kpis"] if kpi.get("column") == measure_key), None)
    if headline is None or abs(Decimal(str(headline["value"])) - expected_total) > Decimal("0.01"):
        failures.append(f"{config['measure']} headline differs from source")
    context = record_context(computed["statistics"])
    if not context or context.get("kind") != "sales_transaction":
        failures.append("Sales rows are not given a plain-language record name")
    result = {
        "dataset": name, "source": str(path), "source_facts": source,
        "zephyr_rows": computed["row_count"],
        "zephyr_total": str(actual_total) if actual_total is not None else None,
        "zephyr_blanks": frame[measure_key].null_count() if measure_key in frame.columns else None,
        "zephyr_group_totals": {key: str(value) for key, value in displayed_totals.items()},
        "record_context": context,
        "forecasts": len(computed["forecasts"]),
        "chart_titles": [chart.get("title") for chart in computed["charts"]],
        "kpi_columns": [kpi.get("column") for kpi in computed["kpis"]],
        "executive_summary": computed["ai_result"].get("executive_summary") if with_ai else None,
        "insights": computed["ai_result"].get("insights") if with_ai else None,
        "recommendations": computed["recommendations"],
        "ai_generation": computed["ai_result"].get("generation") if with_ai else None,
        "passed": not failures, "failures": failures,
    }
    return result


async def main(coffee: Path, supermarket: Path, *, with_ai: bool) -> int:
    print("Preparing Kaggle evaluation", file=sys.stderr, flush=True)
    results = []
    workdir = Path(__file__).resolve().parents[3] / "tmp" / "kaggle" / "eval_artifacts"
    workdir.mkdir(parents=True, exist_ok=True)
    for name, path in (("coffee", coffee), ("supermarket", supermarket)):
        try:
            results.append(await run_case(name, path.resolve(), workdir, with_ai=with_ai))
        except Exception as exc:
            results.append({"dataset": name, "passed": False,
                            "failures": [f"{type(exc).__name__}: {exc}"]})
    print(json.dumps({"offline": not with_ai, "results": results}, indent=2, default=str))
    return int(any(not result["passed"] for result in results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--coffee", type=Path, required=True)
    parser.add_argument("--supermarket", type=Path, required=True)
    parser.add_argument("--with-ai", action="store_true", help="Include live AI wording checks (uses API credits)")
    args = parser.parse_args()
    print("Parsed Kaggle evaluation arguments", file=sys.stderr, flush=True)
    os.environ["DEBUG"] = "false"
    _bootstrap_env(not args.with_ai)
    print("Bootstrapped Kaggle evaluation", file=sys.stderr, flush=True)
    raise SystemExit(asyncio.run(main(args.coffee, args.supermarket, with_ai=args.with_ai)))
