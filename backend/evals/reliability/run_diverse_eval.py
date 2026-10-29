"""Review real local files from several domains through the production pipeline.

The files remain local. Pass each as --dataset name=/path/to/file. This emits
compact, human-readable evidence for a manual clarity review and never calls AI.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import AsyncMock, patch

from openpyxl import load_workbook

from app.analytics.histogram_presentation import present_histogram
from app.analytics.line_presentation import present_time_line
from app.analytics.record_context import record_context
from app.analytics.report_relevance import useful_charts, useful_insights
from app.api.v1.endpoints.analyses import _cleaning_options
from app.services.analysis_engine import compute_analysis
from app.services.export_service import build_excel_report, build_pdf_report
from app.services.file_processor import FileProcessor
from app.services.report_language import present_insight, present_metadata
from app.services.semantic_wrangler import SemanticWrangler, _fallback_display_metadata
from evals.calibration.run_eval import _bootstrap_env, _OfflineAIService


def _source_csv_rows(path: Path) -> int | None:
    if path.suffix.lower() not in {".csv", ".tsv"}:
        return None
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        return max(0, sum(1 for _ in csv.reader(handle)) - 1)


async def run_case(name: str, path: Path, output: Path, save_artifacts: bool = False) -> dict:
    processor = FileProcessor()
    profile = await processor.clean_file(
        str(path), path.suffix.lower(), str(output / f"{name}.parquet"),
        str(output / f"{name}.csv"), _cleaning_options({"mode": "clean"}),
    )
    with patch.object(SemanticWrangler, "build_display_metadata", new_callable=AsyncMock) as display:
        display.side_effect = lambda **kwargs: _fallback_display_metadata(
            kwargs["statistics"], kwargs["charts"]
        )
        computed = await compute_analysis(
            file_processor=processor,
            ai_service=_OfflineAIService(),
            storage_path=str(output / f"{name}.parquet"),
            file_name=path.name,
            analysis_id=f"diverse-{name}",
            upload_context={"cleaning": {"enabled": True, "report": profile["cleaning_report"]}},
        )
    stats = computed["statistics"]
    context = record_context(stats)
    presented_metadata, summary = present_metadata(stats, computed["ai_result"].get("executive_summary"))
    summary = summary or ""
    limitations = ((presented_metadata or {}).get("analysis_evidence") or {}).get("limitations") or []
    charts = useful_charts([present_time_line(present_histogram(chart, context))
                            for chart in computed["charts"]])
    recommendations = useful_insights([
        present_insight({**rec, "type": "recommendation", "data": {
            "problem": rec.get("problem"), "evidence": rec.get("evidence"),
            "expected_impact": rec.get("expected_impact"),
            "confidence_source": rec.get("confidence_source"),
            **(rec.get("data") or {}),
        }}, stats)
        for rec in computed["recommendations"]
    ])
    insights = useful_insights([
        present_insight({**insight, "type": insight.get("type", "insight")}, stats)
        for insight in computed["ai_result"].get("insights", [])
    ])
    pdf = build_pdf_report(
        name=path.stem, row_count=computed["row_count"],
        column_count=len(stats["schema"]), summary=summary,
        insights=[*insights, *recommendations], charts=charts,
        limitations=limitations,
    )
    excel = build_excel_report(
        name=path.stem, row_count=computed["row_count"],
        column_count=len(stats["schema"]), summary=summary,
        insights=[*insights, *recommendations], charts=charts,
        limitations=limitations,
    )
    if save_artifacts:
        (output / f"{name}.pdf").write_bytes(pdf)
        (output / f"{name}.xlsx").write_bytes(excel)
    from io import BytesIO

    workbook = load_workbook(BytesIO(excel), read_only=False)
    flags = []
    if context is None:
        flags.append("Unknown record type: summary may say only 'entries'.")
    if re.search(r"\b(entries|fields|columns|KPIs?|distinct values|model range)\b", summary, re.I):
        flags.append("Summary contains a generic or technical term.")
    visible_text = "\n".join([
        *(chart.get("description") or "" for chart in charts),
        *(item.get("title") or "" for item in recommendations),
        *(item.get("description") or "" for item in recommendations),
        *((item.get("data") or {}).get("evidence") or "" for item in recommendations),
        *limitations,
    ])
    if re.search(r"\b(entries|columns|KPIs?|distinct values|model range)\b|T00:00:00", visible_text, re.I):
        flags.append("A chart, action, or limitation contains generic or technical wording.")
    if not charts:
        flags.append("No useful charts were produced.")
    source_rows = _source_csv_rows(path)
    if source_rows is not None and source_rows != profile["cleaning_report"].get("input_rows"):
        flags.append("Imported CSV row count differs from source row count.")
    return {
        "dataset": name, "file_type": path.suffix.lower(),
        "source_csv_rows": source_rows, "analysed_rows": computed["row_count"],
        "imported_rows": profile["cleaning_report"].get("input_rows"),
        "removed_rows": profile["cleaning_report"].get("input_rows", 0) - computed["row_count"],
        "record_type": (context or {}).get("plural"),
        "schema": [{"name": col["name"], "role": col.get("analysis_role")}
                   for col in stats["schema"][:30]],
        "analysis_schema": [{"name": col["name"], "role": col.get("analysis_role"),
                             "label": col.get("display_label"), "is_date": col.get("is_date")}
                            for col in stats["schema"][:40]],
        "kpis": [{"column": item.get("column"), "value": item.get("value")}
                 for item in computed["kpis"][:8]],
        "excluded_sheets": (stats.get("parser") or {}).get("excluded_sheets"),
        "summary": summary,
        "limitations": limitations,
        "chart_titles": [chart.get("title") for chart in charts],
        "chart_descriptions": [chart.get("description") for chart in charts],
        "chart_axes": [{"title": chart.get("title"), "x": chart.get("xAxis"),
                        "y": chart.get("yAxis")} for chart in charts],
        "recommendation_titles": [item.get("title") for item in recommendations],
        "recommendation_details": [{"title": item.get("title"),
                                     "description": item.get("description"),
                                     "evidence": (item.get("data") or {}).get("evidence"),
                                     "column": (item.get("data") or {}).get("column")}
                                    for item in recommendations],
        "insight_titles": [item.get("title") for item in insights],
        "quality_score": (stats.get("data_quality") or {}).get("score"),
        "quality_issues": [{"type": item.get("type"), "column": item.get("column"),
                            "affected_rows": item.get("affected_rows")}
                           for item in (stats.get("data_quality") or {}).get("issues", [])[:20]],
        "pdf_bytes": len(pdf),
        "excel_chart_count": len(workbook["Charts"]._charts) if "Charts" in workbook else 0,
        "flags": flags,
    }


async def main(datasets: list[str], artifact_dir: Path | None = None) -> int:
    results = []
    context = nullcontext(artifact_dir) if artifact_dir else tempfile.TemporaryDirectory(prefix="zephyr-diverse-eval-")
    with context as temp:
        output = Path(temp)
        output.mkdir(parents=True, exist_ok=True)
        for item in datasets:
            name, sep, raw = item.partition("=")
            if not sep or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                raise ValueError(f"Expected name=path: {item}")
            path = Path(raw).resolve()
            if not path.is_file():
                raise FileNotFoundError(path)
            print(f"Analysing {name}", file=sys.stderr, flush=True)
            try:
                results.append(await run_case(name, path, output, bool(artifact_dir)))
            except Exception as exc:
                results.append({"dataset": name, "error": f"{type(exc).__name__}: {exc}"})
    print(json.dumps({"results": results}, indent=2, default=str))
    return int(any("error" in result for result in results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", action="append", required=True)
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    _bootstrap_env(True)
    raise SystemExit(asyncio.run(main(args.dataset, args.artifact_dir)))
