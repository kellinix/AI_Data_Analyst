"""Rebuild a structured survey report from the original upload, without AI."""
from __future__ import annotations

import asyncio
import sys
import uuid
from copy import deepcopy
from pathlib import Path

import duckdb
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.analytics.analysis_evidence import analysis_evidence
from app.analytics.chart_selector import select_charts
from app.analytics.chart_specs import attach_visual_specs
from app.analytics.live_filter import populate_chart_option
from app.analytics.statistics import StatisticsEngine
from app.analytics.survey_context import clarify_survey, survey_catalog, survey_fields
from app.db.session import AsyncSessionLocal
from app.models.analysis import Analysis, UploadedFile
from app.services.data_profile import build_data_profile_schema, write_data_profile_schema
from app.services.file_processor import FileProcessor


async def repair(analysis_id: str) -> None:
    async with AsyncSessionLocal() as db:
        analysis = (await db.execute(select(Analysis).where(Analysis.id == analysis_id).options(
            selectinload(Analysis.file), selectinload(Analysis.insights)))).scalar_one()
        context = deepcopy((analysis.metadata_ or {}).get("upload_context") or {})
        source_id = context.get("cleaning", {}).get("source_file_id")
        source = (await db.execute(select(UploadedFile).where(UploadedFile.id == source_id,
            UploadedFile.user_id == analysis.user_id))).scalar_one()
        processor = FileProcessor()
        raw, truncated = processor._read_file_ex(source.storage_path, Path(source.storage_path).suffix)
        if truncated:
            raise ValueError("Repair requires the full source file.")
        cleaned, cleaning_report = processor.clean_dataframe(raw, {"semantic_categorical_merging": False})
        if not survey_fields([{"name": name} for name in cleaned.columns]):
            raise ValueError("Source does not contain a structured survey percentage table.")
        if cleaned.height != raw.height:
            raise ValueError("Unexpected row removal; repair was not applied.")
        target = Path(source.storage_path).with_name(f"{uuid.uuid4()}.repaired.parquet")
        cleaned.write_parquet(target)
        csv_path = target.with_suffix(".csv")
        cleaned.write_csv(csv_path)
        profile = processor._profile_dataframe(cleaned)
        replacement = UploadedFile(user_id=analysis.user_id, filename=target.name,
            original_filename=source.original_filename.replace(".csv", " cleaned.parquet"),
            file_size=target.stat().st_size, mime_type="application/octet-stream", storage_path=str(target),
            row_count=cleaned.height, column_count=len(cleaned.columns), columns=profile["columns"])
        db.add(replacement)
        await db.flush()
        context["cleaning"] = {"enabled": True, "mode": "clean", "source_file_id": str(source.id),
            "cleaned_file_id": str(replacement.id), "source_filename": source.original_filename,
            "cleaned_parquet_path": str(target), "cleaned_csv_path": str(csv_path), "report": cleaning_report}
        context["files"] = [{"id": str(source.id), "name": source.original_filename,
            "row_count": raw.height, "column_count": len(raw.columns), "columns": raw.columns}]
        conn = duckdb.connect()
        try:
            conn.register("data", cleaned.to_arrow())
            statistics = StatisticsEngine(conn).describe_all()
            clarify_survey(statistics)
            survey_catalog(statistics, conn)
            statistics["data_quality"]["source_quality"] = cleaning_report["source_quality"]
            statistics["analysis_evidence"] = analysis_evidence(statistics, context)
            statistics["analysis_evidence"]["summary_checks"] = {"method": "survey_measured_v1", "facts": []}
            charts = select_charts(statistics["schema"], statistics["numeric_stats"], statistics["categorical_stats"], {}, {})
            for chart in charts:
                if not populate_chart_option(conn, chart):
                    raise ValueError("Survey chart could not be populated.")
            charts = attach_visual_specs(charts)
        finally:
            conn.close()
        count = statistics["numeric_stats"][survey_fields(statistics["schema"])["percentage"]]["count"]
        questions = statistics["categorical_stats"]["question_code"]["unique_count"]
        summary = (f"This file contains {raw.height:,} survey result records covering {questions} questions, not individual respondents.\n"
            f"{count:,} records contain a published percentage; {raw.height - count:,} remain unavailable and have not been filled in. Blank notes are optional.\n"
            "Each result belongs to a country, survey group, question and answer. These percentages must not be averaged across unrelated questions.\n"
            "The chart shows one explicitly labelled selection. Use the question, answer and survey-group filters to explore other results. Supplied Average rows are excluded from country comparisons.\n"
            "No overall population percentage, respondent count or trend is inferred from this table.")
        profile_json = build_data_profile_schema(analysis_id=str(analysis.id), file_name=source.original_filename,
            statistics=statistics, kpis=[], charts=charts, forecasts=[], anomalies=[], recommendations=[], upload_context=context)
        profile_path = write_data_profile_schema(profile_json, target.with_suffix(".profile.json"))
        metadata = {**statistics, "data_profile": profile_json, "profile_json_path": profile_path,
            "upload_context": context, "forecasts": [], "anomalies": [], "ai_generation": {"status": "deterministic_repair"},
            "superseded_file_id": str(analysis.file_id)}
        # The original upload and previous cleaned artifact remain intact.
        for insight in analysis.insights:
            await db.delete(insight)
        original_profile = processor._profile_dataframe(raw)
        source.row_count, source.column_count, source.columns = raw.height, len(raw.columns), original_profile["columns"]
        analysis.file_id = replacement.id
        analysis.row_count, analysis.column_count = cleaned.height, len(cleaned.columns)
        analysis.metadata_, analysis.charts, analysis.summary = metadata, charts, summary
        await db.commit()
        print(f"Rebuilt survey report: {raw.height} records, {questions} question codes, {count} published percentages; no AI request.")


if __name__ == "__main__":
    asyncio.run(repair(sys.argv[1]))
