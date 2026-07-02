from __future__ import annotations

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

import uuid
from pathlib import Path
from typing import Any

import duckdb
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.analytics.anomaly_detection import detect_anomalies
from app.analytics.chart_selector import select_charts
from app.analytics.chart_specs import attach_visual_specs
from app.analytics.forecasting import generate_forecasts
from app.analytics.kpi_detector import detect_kpis
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
        row_count = await self.file_processor.read_to_duckdb(
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
        """Query DuckDB to populate chart series data."""
        populated = []
        for chart in charts:
            try:
                opt = chart.get("echarts_option", {})
                cols = opt.get("_columns", {})
                x_col = cols.get("x")
                y_col = cols.get("y")
                cat_col = cols.get("category")
                y_cols = cols.get("ys", [])
                orientation = cols.get("orientation")

                if chart["type"] == "line" and x_col and y_cols:
                    select_columns = ", ".join(
                        f"AVG({_quote_identifier(col)}) AS {_quote_identifier(col)}"
                        for col in y_cols
                    )
                    x_identifier = _quote_identifier(x_col)
                    rows = conn.execute(f"""
                        SELECT CAST({x_identifier} AS VARCHAR) AS period, {select_columns}
                        FROM data
                        WHERE {x_identifier} IS NOT NULL
                        GROUP BY {x_identifier}
                        ORDER BY {x_identifier}
                        LIMIT 100
                    """).fetchall()
                    x_data = [str(r[0]) for r in rows]
                    opt["xAxis"]["data"] = x_data
                    for index, col in enumerate(y_cols):
                        opt["series"][index]["data"] = [
                            round(float(r[index + 1]), 2) if r[index + 1] is not None else 0
                            for r in rows
                        ]

                elif chart["type"] == "line" and x_col and y_col:
                    x_identifier = _quote_identifier(x_col)
                    y_identifier = _quote_identifier(y_col)
                    rows = conn.execute(f"""
                        SELECT CAST({x_identifier} AS VARCHAR), AVG({y_identifier})
                        FROM data
                        WHERE {x_identifier} IS NOT NULL AND {y_identifier} IS NOT NULL
                        GROUP BY {x_identifier}
                        ORDER BY {x_identifier}
                        LIMIT 100
                    """).fetchall()
                    x_data = [str(r[0]) for r in rows]
                    y_data = [round(float(r[1]), 2) if r[1] is not None else 0 for r in rows]
                    opt["xAxis"]["data"] = x_data
                    opt["series"][0]["data"] = y_data

                elif chart["type"] == "bar" and x_col and y_col:
                    x_identifier = _quote_identifier(x_col)
                    y_identifier = _quote_identifier(y_col)
                    rows = conn.execute(f"""
                        SELECT CAST({x_identifier} AS VARCHAR), SUM({y_identifier}) as value
                        FROM data
                        WHERE {x_identifier} IS NOT NULL AND {y_identifier} IS NOT NULL
                        GROUP BY {x_identifier}
                        ORDER BY value DESC
                        LIMIT 15
                    """).fetchall()
                    labels = [str(r[0]) for r in rows]
                    values = [round(float(r[1]), 2) for r in rows]
                    if orientation == "horizontal":
                        opt["yAxis"]["data"] = labels[::-1]
                        opt["series"][0]["data"] = values[::-1]
                    else:
                        opt["xAxis"]["data"] = labels
                        opt["series"][0]["data"] = values

                elif chart["type"] == "donut" and cat_col:
                    cat_identifier = _quote_identifier(cat_col)
                    rows = conn.execute(f"""
                        SELECT CAST({cat_identifier} AS VARCHAR), COUNT(*) as cnt
                        FROM data
                        WHERE {cat_identifier} IS NOT NULL
                        GROUP BY {cat_identifier}
                        ORDER BY cnt DESC
                        LIMIT 8
                    """).fetchall()
                    opt["series"][0]["data"] = [
                        {"name": str(r[0]), "value": int(r[1])} for r in rows
                    ]

                elif chart["type"] == "scatter" and x_col and y_col:
                    x_identifier = _quote_identifier(x_col)
                    y_identifier = _quote_identifier(y_col)
                    rows = conn.execute(f"""
                        SELECT {x_identifier}, {y_identifier}
                        FROM data
                        WHERE {x_identifier} IS NOT NULL AND {y_identifier} IS NOT NULL
                        LIMIT 500
                    """).fetchall()
                    opt["series"][0]["data"] = [[float(r[0]), float(r[1])] for r in rows if r[0] is not None and r[1] is not None]

                elif chart["type"] == "histogram" and x_col:
                    x_identifier = _quote_identifier(x_col)
                    rows = conn.execute(f"""
                        SELECT {x_identifier}
                        FROM data
                        WHERE {x_identifier} IS NOT NULL
                        LIMIT 10000
                    """).fetchall()
                    values = [float(row[0]) for row in rows if row[0] is not None]
                    if values:
                        min_value = min(values)
                        max_value = max(values)
                        bucket_count = min(12, max(1, len(set(values))))
                        if min_value == max_value:
                            opt["xAxis"]["data"] = [f"{min_value:.0f}"]
                            opt["series"][0]["data"] = [len(values)]
                        else:
                            bucket_size = (max_value - min_value) / bucket_count
                            counts = [0 for _ in range(bucket_count)]
                            for value in values:
                                index = int((value - min_value) / bucket_size)
                                index = min(index, bucket_count - 1)
                                counts[index] += 1
                            opt["xAxis"]["data"] = [
                                f"{min_value + (i * bucket_size):.0f}-{min_value + ((i + 1) * bucket_size):.0f}"
                                for i in range(bucket_count)
                            ]
                            opt["series"][0]["data"] = counts

                # Remove internal _columns hint
                opt.pop("_columns", None)
                chart["echarts_option"] = opt
                populated.append(chart)
            except Exception as exc:
                logger.warning("Chart data population failed", chart_type=chart.get("type"), exc=str(exc))
                opt.pop("_columns", None)
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
            insight = Insight(
                analysis_id=analysis.id,
                type="summary",
                title=kpi_label,
                description=f"Total {kpi_label}: {kpi['value']:,.2f}" if kpi.get("is_currency") else f"{kpi_label}: {kpi['value']:,}",
                importance="high",
                confidence=0.99,
                sort_order=i,
                data={
                    "value": kpi.get("value"),
                    "is_currency": kpi.get("is_currency", False),
                    "kpi_type": kpi.get("kpi_type"),
                    "mean": kpi.get("mean"),
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
            insight = Insight(
                analysis_id=analysis.id,
                type="forecast",
                title=f"{forecast['metric']} forecast",
                description=(
                    f"Next month is forecast at {next_month.get('value', 0):,.2f} "
                    f"with a confidence interval of {next_month.get('lower', 0):,.2f} to {next_month.get('upper', 0):,.2f}."
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
    for recommendation in [*ai_recommendations, *deterministic_recommendations]:
        title = str(recommendation.get("title", "")).strip()
        key = _recommendation_key(recommendation)
        if not title or key in seen_titles:
            continue
        seen_titles.add(key)
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


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
