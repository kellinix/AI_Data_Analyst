"""
Analysis Engine — Orchestrates the full pipeline for a single analysis.

Pipeline:
1. Load file → DuckDB
2. Compute statistics (StatisticsEngine)
3. Detect KPIs (kpi_detector)
4. Select charts (chart_selector)
5. Generate AI insights + summary (AIService)
6. Persist results to DB
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import duckdb
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.analytics.anomaly_detection import detect_anomalies
from app.analytics.chart_selector import select_charts
from app.analytics.chart_specs import attach_visual_specs
from app.analytics.forecasting import generate_forecasts
from app.analytics.kpi_detector import detect_kpis
from app.analytics.live_filter import populate_chart_option
from app.analytics.recommendations import generate_recommendations
from app.analytics.statistics import StatisticsEngine
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.analysis import Analysis, AnalysisStatus, UploadedFile
from app.models.insight import Insight
from app.services.ai_service import AIService
from app.services.data_profile import build_data_profile_schema, write_data_profile_schema
from app.services.file_processor import FileProcessor
from app.services.semantic_wrangler import (
    SemanticWrangler,
    apply_display_metadata_to_charts,
    apply_display_metadata_to_statistics,
)

logger = get_logger(__name__)


class AnalysisEngine:
    """Runs the complete analysis pipeline for a given analysis ID."""

    def __init__(self) -> None:
        self.file_processor = FileProcessor()
        self.ai_service = AIService()

    async def run(self, analysis_id: str) -> None:
        async with AsyncSessionLocal() as db:
            try:
                await self._run_pipeline(db, analysis_id)
                await db.commit()
            except Exception as exc:
                logger.error("Analysis pipeline failed", analysis_id=analysis_id, exc=str(exc))
                await self._mark_failed(db, analysis_id, str(exc))
                await db.commit()
                raise

    async def _run_pipeline(self, db: AsyncSession, analysis_id: str) -> None:
        # Fetch analysis + file
        result = await db.execute(
            select(Analysis)
            .where(Analysis.id == uuid.UUID(analysis_id))
            .options(selectinload(Analysis.file))
        )
        analysis = result.scalar_one_or_none()
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")

        uploaded_file: UploadedFile = analysis.file
        upload_context = (analysis.metadata_ or {}).get("upload_context")

        # Mark processing
        await self._update_progress(db, analysis, AnalysisStatus.PROCESSING, 5)

        # Step 1: Load into DuckDB
        conn = duckdb.connect(":memory:")
        extension = Path(uploaded_file.storage_path).suffix.lower()
        row_count, truncated = await self.file_processor.read_to_duckdb_ex(
            conn, uploaded_file.storage_path, extension
        )
        await self._update_progress(db, analysis, AnalysisStatus.PROCESSING, 15)

        # Step 2: Compute statistics
        stats_engine = StatisticsEngine(conn)
        statistics = stats_engine.describe_all()
        statistics["parser"] = self.file_processor._parser_metadata(
            uploaded_file.storage_path,
            extension,
        )
        if truncated:
            statistics["sample_truncated"] = True
            statistics["sample_row_limit"] = self.file_processor.SAMPLE_ROWS
        _adjust_portfolio_data_quality(statistics, upload_context)
        uploaded_file.row_count = row_count
        uploaded_file.column_count = len(statistics["schema"])
        uploaded_file.columns = statistics["schema"]
        await self._update_progress(db, analysis, AnalysisStatus.PROCESSING, 35)

        # Step 3: Detect KPIs
        kpis = detect_kpis(
            schema=statistics["schema"],
            numeric_stats=statistics["numeric_stats"],
        )
        await self._update_progress(db, analysis, AnalysisStatus.PROCESSING, 50)

        # Step 4: Select charts
        charts = select_charts(
            schema=statistics["schema"],
            numeric_stats=statistics["numeric_stats"],
            categorical_stats=statistics["categorical_stats"],
            date_range=statistics["date_range"],
            correlations=statistics["correlations"],
        )

        # Populate chart data from DuckDB
        charts = await self._populate_chart_data(conn, charts)
        semantic_display = await SemanticWrangler().build_display_metadata(
            file_name=uploaded_file.original_filename,
            statistics=statistics,
            charts=charts,
            upload_context=upload_context,
        )
        statistics = apply_display_metadata_to_statistics(statistics, semantic_display)
        charts = apply_display_metadata_to_charts(charts, semantic_display)
        charts = attach_visual_specs(charts)
        await self._update_progress(db, analysis, AnalysisStatus.PROCESSING, 65)

        # Step 5: Forecasting, anomalies, and deterministic recommendations
        forecasts = generate_forecasts(conn, statistics["schema"], kpis)
        anomalies = detect_anomalies(conn, statistics["schema"], statistics["numeric_stats"])
        deterministic_recommendations = generate_recommendations(
            kpis=kpis,
            data_quality=statistics["data_quality"],
            anomalies=anomalies,
            forecasts=forecasts,
        )
        profile_json = build_data_profile_schema(
            analysis_id=analysis_id,
            file_name=uploaded_file.original_filename,
            statistics={
                **statistics,
                "forecasts": forecasts,
                "anomalies": anomalies,
                "deterministic_recommendations": deterministic_recommendations,
                "upload_context": upload_context,
                "semantic_display": semantic_display,
            },
            kpis=kpis,
            charts=charts,
            forecasts=forecasts,
            anomalies=anomalies,
            recommendations=deterministic_recommendations,
            upload_context=upload_context,
        )
        profile_json_path = write_data_profile_schema(
            profile_json,
            Path(uploaded_file.storage_path).with_name(f"{analysis_id}.profile.json"),
        )
        await self._update_progress(db, analysis, AnalysisStatus.PROCESSING, 75)

        # Step 6: AI generation grounded in computed metrics
        ai_result = await self.ai_service.generate_analysis(
            file_name=uploaded_file.original_filename,
            statistics={
                **statistics,
                "forecasts": forecasts,
                "anomalies": anomalies,
                "deterministic_recommendations": deterministic_recommendations,
                "upload_context": upload_context,
                "profile_json": profile_json,
                "profile_json_path": profile_json_path,
                "semantic_display": semantic_display,
            },
            kpis=kpis,
        )
        await self._update_progress(db, analysis, AnalysisStatus.PROCESSING, 85)

        ai_recommendations = ai_result.get("recommendations", [])
        recommendations = _merge_recommendations(
            ai_recommendations,
            deterministic_recommendations,
        )
        await self._update_progress(db, analysis, AnalysisStatus.PROCESSING, 90)

        # Step 7: Persist
        await self._persist_results(
            db=db,
            analysis=analysis,
            row_count=row_count,
            column_count=len(statistics["schema"]),
            summary=ai_result.get("executive_summary", ""),
            charts=charts,
            kpis=kpis,
            ai_insights=ai_result.get("insights", []),
            ai_recommendations=recommendations,
            metadata={
                **statistics,
                "forecasts": forecasts,
                "anomalies": anomalies,
                "upload_context": upload_context,
                "profile_json": profile_json,
                "profile_json_path": profile_json_path,
                "semantic_display": semantic_display,
                "ai_layout_grid": ai_result.get("layout_grid", []),
            },
        )

        conn.close()
        logger.info("Analysis completed", analysis_id=analysis_id)

    async def _populate_chart_data(
        self, conn: duckdb.DuckDBPyConnection, charts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Query DuckDB to populate chart series data.

        `_columns` is intentionally kept on the stored `echarts_option` (not
        popped) — the live-filter endpoint (`app.analytics.live_filter`)
        reuses it to re-run this exact same aggregation with a WHERE clause,
        so a filtered view can never drift from how this chart was built.
        """
        populated = []
        for chart in charts:
            try:
                populate_chart_option(conn, chart)
                populated.append(chart)
            except Exception as exc:
                logger.warning("Chart data population failed", chart_type=chart.get("type"), exc=str(exc))
                populated.append(chart)

        return populated

    async def _persist_results(
        self,
        db: AsyncSession,
        analysis: Analysis,
        row_count: int,
        column_count: int,
        summary: str,
        charts: list[dict[str, Any]],
        kpis: list[dict[str, Any]],
        ai_insights: list[dict[str, Any]],
        ai_recommendations: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> None:
        await db.execute(delete(Insight).where(Insight.analysis_id == analysis.id))
        display_labels = {
            str(item.get("name")): str(item.get("label"))
            for item in (metadata.get("semantic_display") or {}).get("columns", [])
            if isinstance(item, dict) and item.get("name") and item.get("label")
        }

        # KPI insights (type=summary)
        for i, kpi in enumerate(kpis):
            kpi_label = display_labels.get(
                kpi["column"],
                kpi["column"].replace("_", " ").title(),
            )
            is_total = kpi.get("is_total", True)
            is_percent = kpi.get("is_percent", False)
            if is_percent:
                title = f"{kpi_label} Rate"
                description = f"{kpi['value']:,.1f}% of records have {kpi_label.lower()} = 1"
            elif is_total:
                title = kpi_label
                description = f"{kpi_label}: {kpi['value']:,}"
            else:
                title = f"Avg {kpi_label}"
                description = f"Average {kpi_label}: {kpi['value']:,.2f}"
            if kpi.get("is_currency"):
                value_word = "Total" if is_total else "Average"
                description = f"{value_word} {kpi_label}: {kpi['value']:,.2f}"
            insight = Insight(
                analysis_id=analysis.id,
                type="summary",
                title=title,
                description=description,
                importance="high",
                confidence=0.99,
                sort_order=i,
                data={
                    "value": kpi.get("value"),
                    "is_currency": kpi.get("is_currency", False),
                    "is_percent": is_percent,
                    "kpi_type": kpi.get("kpi_type"),
                    "mean": kpi.get("mean"),
                    "column": kpi["column"],
                    "is_total": is_total,
                },
            )
            db.add(insight)

        # AI insights
        for i, ai_insight in enumerate(ai_insights[:12]):
            insight = Insight(
                analysis_id=analysis.id,
                type=ai_insight.get("type", "trend"),
                title=ai_insight.get("title", "Insight"),
                description=ai_insight.get("description", ""),
                importance=ai_insight.get("importance", "medium"),
                confidence=min(max(float(ai_insight.get("confidence", 0.8)), 0.0), 1.0),
                sort_order=100 + i,
                data=ai_insight.get("data", {}),
            )
            db.add(insight)

        # Forecast insights
        for i, forecast in enumerate(metadata.get("forecasts", [])[:3]):
            next_month = forecast.get("predictions", {}).get("next_month", {})
            metric_label = _humanize_metric_label(forecast["metric"])
            insight = Insight(
                analysis_id=analysis.id,
                type="forecast",
                title=f"{metric_label} forecast",
                description=(
                    f"Next month is forecast at {next_month.get('value', 0):,.2f}, "
                    f"likely to fall somewhere between {next_month.get('lower', 0):,.2f} "
                    f"and {next_month.get('upper', 0):,.2f}."
                ),
                importance="medium",
                confidence=float(forecast.get("confidence", 0.7)),
                sort_order=150 + i,
                data=forecast,
            )
            db.add(insight)

        # Anomaly insights
        for i, anomaly in enumerate(metadata.get("anomalies", [])[:5]):
            insight = Insight(
                analysis_id=analysis.id,
                type="anomaly",
                title=anomaly.get("title", "Anomaly detected"),
                description=anomaly.get("description", ""),
                importance="high",
                confidence=min(float(anomaly.get("score", 0)) / 5, 0.95),
                sort_order=175 + i,
                data=anomaly,
            )
            db.add(insight)

        # AI recommendations
        for i, rec in enumerate(ai_recommendations[:8]):
            rec_data = rec.get("data", {})
            normalized_data = {
                "problem": rec.get("problem"),
                "evidence": rec.get("evidence"),
                "expected_impact": rec.get("expected_impact"),
                "financial_opportunity": rec.get("financial_opportunity"),
                "show_financial_opportunity": bool(rec.get("show_financial_opportunity")),
                "difficulty": rec.get("difficulty"),
                "owner": rec.get("owner"),
                "estimated_completion": rec.get("estimated_completion"),
                **rec_data,
            }
            insight = Insight(
                analysis_id=analysis.id,
                type="recommendation",
                title=rec.get("title", "Recommendation"),
                description=rec.get("description", ""),
                importance=rec.get("importance", "medium"),
                confidence=min(max(float(rec.get("confidence", 0.8)), 0.0), 1.0),
                sort_order=200 + i,
                data=normalized_data,
            )
            db.add(insight)

        # Update analysis
        analysis.status = AnalysisStatus.COMPLETED.value
        analysis.progress = 100
        analysis.row_count = row_count
        analysis.column_count = column_count
        analysis.summary = summary
        analysis.charts = charts
        analysis.metadata_ = {
            "upload_context": metadata.get("upload_context"),
            "data_quality": metadata.get("data_quality", {}),
            "date_range": metadata.get("date_range", {}),
            "schema": metadata.get("schema", []),
            "parser": metadata.get("parser", {}),
            "profile_json_path": metadata.get("profile_json_path"),
            "data_profile": metadata.get("profile_json", {}),
            "semantic_display": metadata.get("semantic_display", {}),
            "forecasts": metadata.get("forecasts", []),
            "anomalies": metadata.get("anomalies", []),
        }

        await db.flush()

    async def _update_progress(
        self, db: AsyncSession, analysis: Analysis, status: AnalysisStatus, progress: int
    ) -> None:
        analysis.status = status.value
        analysis.progress = progress
        await db.flush()
        await db.commit()

    async def _mark_failed(self, db: AsyncSession, analysis_id: str, error: str) -> None:
        result = await db.execute(
            select(Analysis).where(Analysis.id == uuid.UUID(analysis_id))
        )
        analysis = result.scalar_one_or_none()
        if analysis:
            analysis.status = AnalysisStatus.FAILED.value
            analysis.error_message = error[:1024]
            await db.flush()


def _merge_recommendations(
    ai_recommendations: list[dict[str, Any]],
    deterministic_recommendations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    seen_evidence: set[str] = set()
    for recommendation in [*ai_recommendations, *deterministic_recommendations]:
        title = str(recommendation.get("title", "")).strip()
        key = _recommendation_key(recommendation)
        # Two cards citing the same evidence are the same finding worded
        # differently (an AI card and a deterministic card for one anomaly).
        evidence = " ".join(str(recommendation.get("evidence", "")).lower().split())
        if not title or key in seen_titles:
            continue
        if evidence and evidence in seen_evidence:
            continue
        seen_titles.add(key)
        if evidence:
            seen_evidence.add(evidence)
        merged.append(recommendation)
    return merged[:8]


def _adjust_portfolio_data_quality(
    statistics: dict[str, Any],
    upload_context: Any,
) -> None:
    if not isinstance(upload_context, dict):
        return
    if not upload_context.get("combined"):
        return
    if upload_context.get("combine_strategy") != "portfolio":
        return

    data_quality = statistics.get("data_quality")
    if not isinstance(data_quality, dict):
        return

    issues = data_quality.get("issues", [])
    fixes = data_quality.get("fixes", [])
    if not isinstance(issues, list):
        return

    non_missing_issues = [
        issue
        for issue in issues
        if not (isinstance(issue, dict) and issue.get("type") == "missing_values")
    ]
    data_quality["issues"] = non_missing_issues[:25]
    if isinstance(fixes, list):
        data_quality["fixes"] = [
            fix
            for fix in fixes
            if not (
                isinstance(fix, dict)
                and str(fix.get("id", "")).startswith("fill_missing_")
            )
        ][:10]

    if len(non_missing_issues) < len(issues):
        data_quality["portfolio_sparse_schema"] = True
        data_quality["portfolio_note"] = (
            "Missing values caused by row-preserving multi-file portfolio columns "
            "were muted because each source file naturally has different fields."
        )
        data_quality["score"] = max(int(data_quality.get("score") or 0), 95)


def _humanize_metric_label(value: str) -> str:
    return " ".join(word.capitalize() for word in value.replace("_", " ").split())


def _recommendation_key(recommendation: dict[str, Any]) -> str:
    title = str(recommendation.get("title", "")).lower()
    evidence = str(recommendation.get("evidence", "")).lower()
    normalized = " ".join(f"{title} {evidence}".split())
    if "high-volume" in normalized or "high volume" in normalized or "concentration" in normalized:
        for metric in (
            "global business mobility",
            "skilled worker",
        ):
            if metric in normalized:
                return f"volume:{metric}"
        return "volume"
    return normalized
