"""Refresh a saved admission report from its file, without AI or quota usage."""
from __future__ import annotations

import asyncio
import sys
from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.analytics.admission_context import (
    FIELDS,
    admission_summary,
    clarify_chart,
    clarify_statistics,
    is_admission,
)
from app.analytics.chart_selector import select_charts
from app.analytics.chart_specs import attach_visual_specs
from app.analytics.kpi_detector import detect_kpis
from app.analytics.live_filter import populate_chart_option
from app.analytics.statistics import StatisticsEngine
from app.db.session import AsyncSessionLocal
from app.models.analysis import Analysis
from app.models.insight import Insight
from app.services.investigation import _load


async def repair(analysis_id: str) -> None:
    async with AsyncSessionLocal() as db:
        analysis = (await db.execute(select(Analysis).where(Analysis.id == analysis_id).options(
            selectinload(Analysis.file), selectinload(Analysis.insights)))).scalar_one()
        metadata = deepcopy(analysis.metadata_)
        if not is_admission(metadata.get("schema") or []):
            raise ValueError("This report does not have the supported admission schema.")
        clarify_statistics(metadata)
        conn, rows, truncated = await _load(analysis)
        try:
            if truncated:
                raise ValueError("Repair requires the complete analysed file.")
            measured = StatisticsEngine(conn).describe_all()
            for key in ("numeric_stats", "categorical_stats", "correlations", "row_count"):
                metadata[key] = measured[key]
            charts = select_charts(metadata["schema"], metadata["numeric_stats"], metadata.get("categorical_stats", {}),
                metadata.get("date_range", {}), metadata.get("correlations", {}))
            for chart in charts:
                if not populate_chart_option(conn, chart):
                    raise ValueError("Chart data could not be populated.")
                clarify_chart(chart)
            # Keep data measured from the file, not rounded UI or model output.
            for column in FIELDS:
                metadata["numeric_stats"][column]["mean"] = conn.execute(f'SELECT AVG("{column}") FROM data').fetchone()[0]
        finally:
            conn.close()
        existing = {i.data.get("column"): i for i in analysis.insights if i.type == "summary" and i.data}
        for order, kpi in enumerate(detect_kpis(metadata["schema"], metadata["numeric_stats"])):
            column = kpi["column"]
            insight = existing.get(column)
            if insight is None:
                insight = Insight(analysis_id=analysis.id, type="summary", confidence=.99)
                db.add(insight)
            insight.title = "Average undergraduate grade (out of 10)" if column == "cgpa" else f"Average {FIELDS.get(column, (column, None))[0]}"
            insight.description = "Average recorded chance, not the percentage actually admitted." if column == "chance_of_admit" else "Average across applicant records."
            insight.importance, insight.sort_order = "high", order
            insight.data = {**kpi, "is_currency": False, "currency": None}
        for insight in analysis.insights:
            if insight.type == "anomaly" and (insight.data or {}).get("column") == "cgpa":
                insight.importance = "low"
            if insight.type == "recommendation" and (insight.data or {}).get("confidence_source") == "rule:anomaly":
                insight.importance = "low"
        metadata.setdefault("analysis_evidence", {})["summary_checks"] = {
            "method": "admission_measured_v1", "facts": [], "scope": "All analysed applicant records"}
        metadata.pop("presentation_version", None)
        analysis.metadata_ = metadata
        analysis.summary = admission_summary(metadata)
        old_ids = {(chart.get("type"), (chart.get("echarts_option") or {}).get("_columns", {}).get("x"), (chart.get("echarts_option") or {}).get("_columns", {}).get("y")): chart["id"] for chart in analysis.charts or []}
        for chart in charts:
            columns = chart["echarts_option"].get("_columns", {})
            previous_id = old_ids.get((chart["type"], columns.get("x"), columns.get("y")))
            if previous_id:
                chart["id"] = previous_id
        analysis.charts = attach_visual_specs(charts)
        await db.commit()
        print(f"Updated admission report: {rows} records, {len(charts)} focused charts; no AI request.")


if __name__ == "__main__":
    asyncio.run(repair(sys.argv[1]))
