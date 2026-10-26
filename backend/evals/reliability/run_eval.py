"""Run with python -m evals.reliability.run_eval; failures exit nonzero.

Uses synthetic files with known answers, real upload cleaning and analysis,
and an offline AI stub. Does not certify generated AI prose or deployment.
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import tempfile
from pathlib import Path

CASES = {
    "missing_revenue": (["Order ID", "Revenue"], [["001", "100"], ["002", ""], ["003", "30"]]),
    "refunds": (["Order ID", "Revenue"], [["001", "100"], ["002", "-25"], ["003", "0"]]),
    "repeated_transactions": (["Region", "Revenue"], [["West", "50"], ["West", "50"], ["East", "20"]]),
    "identifiers": (["Customer ID", "Postal Code", "Revenue"], [["00001", "00123", "10"], ["00002", "00456", "20"]]),
    "category_codes": (["Product Code", "Revenue"], [["001", "10"], ["01", "20"], ["1", "30"]]),
    "ratings": (["Customer ID", "Rating"], [["001", "1"], ["002", "5"], ["003", "3"]]),
    "optional_notes": (["Order ID", "Revenue", "Notes"], [["001", "10", ""], ["002", "20", "review"]]),
    "survey": (["CountryCode", "subset", "question_code", "question_label", "answer", "percentage", "notes"], [
        ["Italy", "Group A", "b1_a", "Is it widespread?", "Yes", "63", ""],
        ["France", "Group A", "b1_a", "Is it widespread?", "Yes", ":", ""],
        ["Italy", "Group A", "b1_b", "Is it common?", "Yes", "40", ""],
    ]),
}


async def run_case(name: str, workdir: Path, *, reverse: bool = False) -> dict:
    import polars as pl

    from app.api.v1.endpoints.analyses import _cleaning_options
    from app.services.analysis_engine import compute_analysis
    from app.services.file_processor import FileProcessor
    from evals.calibration.run_eval import _OfflineAIService

    headers, rows = CASES[name]
    if reverse:
        rows = list(reversed(rows))
    source = workdir / f"{name}.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    processor = FileProcessor()
    target = workdir / f"{name}.parquet"
    options = _cleaning_options({"mode": "clean"})
    profile = await processor.clean_file(str(source), ".csv", str(target), str(target.with_suffix(".cleaned.csv")), options)
    frame = pl.read_parquet(target)
    failures = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    check(frame.height == len(rows), "Source records were lost or duplicated")
    check(not options["semantic_categorical_merging"], "Default cleaning permits unapproved category merging")
    for index, header in enumerate(headers):
        column = header.lower().replace(" ", "_")
        # Formatting cleanup may remove a wholly blank optional column.
        if all(not row[index] for row in rows):
            continue
        if column not in frame.columns:
            check(False, f"Source column {header} was lost")
            continue
        expected = [row[index] for row in rows]
        if header.endswith((" ID", " Code")):
            check(frame[column].to_list() == expected, f"Identifier values changed: {header}")
        if header in {"Revenue", "Rating", "percentage"}:
            expected_values = [float(value) if value not in {"", ":"} else None for value in expected]
            check(frame[column].to_list() == expected_values, f"Recorded numbers or gaps changed: {header}")
    computed = await compute_analysis(
        file_processor=processor, ai_service=_OfflineAIService(), storage_path=str(target),
        file_name=source.name, analysis_id=name,
        upload_context={"cleaning": {"enabled": True, "report": profile["cleaning_report"]}},
    )
    check(not computed["forecasts"], "Forecast produced without a usable time series")
    check(computed["row_count"] == len(rows), "Analysis record count differs from the source")
    if "Revenue" in headers:
        index = headers.index("Revenue")
        expected_total = sum(float(row[index]) for row in rows if row[index])
        stats = computed["statistics"]["numeric_stats"]["revenue"]
        check(stats["total"] == expected_total, "Reported revenue differs from the recorded total")
    for kpi in computed["kpis"]:
        check(kpi.get("column") not in {"order_id", "customer_id", "postal_code", "product_code"}, "Identifier used as a business measure")
    if name == "survey":
        check(not computed["kpis"], "Unrelated survey percentages combined into an overall measure")
    if name == "ratings":
        check(not any(k.get("is_total") for k in computed["kpis"]), "Ratings presented as a total")
    return {"dataset": name, "reversed": reverse, "passed": not failures, "failures": failures, "rows": frame.height}


async def main() -> int:
    results = []
    with tempfile.TemporaryDirectory(prefix="zephyr-reliability-") as directory:
        for name in CASES:
            for reverse in (False, True):
                try:
                    results.append(await run_case(name, Path(directory), reverse=reverse))
                except Exception as exc:
                    results.append({"dataset": name, "reversed": reverse, "passed": False, "failures": [f"{type(exc).__name__}: {exc}"]})
    report = {"version": 1, "offline": True, "results": results}
    print(json.dumps(report, indent=2))
    return int(any(not result["passed"] for result in results))


if __name__ == "__main__":
    from evals.calibration.run_eval import _bootstrap_env
    os.environ["DEBUG"] = "false"
    _bootstrap_env(True)
    raise SystemExit(asyncio.run(main()))
