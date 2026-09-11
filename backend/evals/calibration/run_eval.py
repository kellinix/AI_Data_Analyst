"""
Run the confidence-calibration benchmark.

    cd backend
    python -m evals.calibration.run_eval                # real AI + LLM judge (needs OPENAI_API_KEY)
    python -m evals.calibration.run_eval --no-ai        # offline: rule-based recommendations only
    python -m evals.calibration.run_eval --rescore      # recompute metrics from saved raw results
    python -m evals.calibration.run_eval --retry-failed # re-run datasets whose AI/judge calls failed
    python -m evals.calibration.run_eval --rejudge      # re-grade saved results with the current judge
    python -m evals.calibration.run_eval --write-table  # also update app/analytics/calibration_table.json

Each dataset goes through the production path: the upload screen's default
cleaning (`_cleaning_options({"mode": "clean"})`, the same helper the
analyses endpoint uses), then `compute_analysis` — the function
`AnalysisEngine` runs. Results land in `evals/calibration/results/`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _bootstrap_env(no_ai: bool) -> None:
    """Settings are built at import time, so the environment must be ready first."""
    os.environ.setdefault("SECRET_KEY", "offline-eval-secret-key-not-used-for-auth")
    os.environ.setdefault("POSTGRES_PASSWORD", "unused-by-the-eval")
    if no_ai:
        os.environ["SEMANTIC_WRANGLING_ENABLED"] = "false"
        os.environ.setdefault("OPENAI_API_KEY", "sk-offline-eval")
        return
    for env_file in (BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            key = key.strip()
            if key in {"OPENAI_API_KEY", "OPENAI_MODEL"} and not os.environ.get(key):
                os.environ[key] = value.strip().strip('"').strip("'")
    if not os.environ.get("OPENAI_API_KEY", "").startswith("sk-"):
        sys.exit("OPENAI_API_KEY is not set (env or .env). Pass --no-ai for an offline run.")


class _OfflineAIService:
    """Stands in for AIService on --no-ai runs: the pipeline's no-AI fallback."""

    async def generate_analysis(self, **_: Any) -> dict[str, Any]:
        return {"executive_summary": "", "layout_grid": [], "insights": [], "recommendations": []}


async def run_dataset(
    scenario: Any,
    workdir: Path,
    *,
    ai_service: Any,
    judge_client: Any = None,
    judge_model: str | None = None,
) -> dict[str, Any]:
    """Generate, clean, analyse, and label one benchmark dataset."""
    from app.api.v1.endpoints.analyses import _cleaning_options
    from app.services.analysis_engine import compute_analysis
    from app.services.file_processor import FileProcessor
    from app.services.semantic_wrangler import SemanticWrangler
    from evals.calibration.benchmark import write_dataset
    from evals.calibration.labels import (
        Label,
        judge_recommendation,
        label_rule_recommendation,
        truth_for_judge,
    )

    csv_path, truth = write_dataset(scenario, workdir)
    processor = FileProcessor()
    options = _cleaning_options({"mode": "clean"})
    parquet_path = workdir / f"{scenario.dataset_id}.cleaned.parquet"
    cleaned_csv_path = workdir / f"{scenario.dataset_id}.cleaned.csv"
    profile = await processor.clean_file(
        str(csv_path), ".csv", str(parquet_path), str(cleaned_csv_path), options
    )
    if options.get("semantic_categorical_merging"):
        profile = await SemanticWrangler().canonicalize_cleaned_file(
            parquet_path=str(parquet_path), csv_path=str(cleaned_csv_path), profile=profile
        )
    upload_context = {
        "analysis_mode": "single",
        "current_file_name": csv_path.name,
        "data_description": None,
        "instructions": None,
        "suggestions": [],
        "cleaning": {
            "enabled": True,
            "mode": "clean",
            "source_filename": csv_path.name,
            "report": profile.get("cleaning_report", {}),
        },
    }
    computed = await compute_analysis(
        file_processor=processor,
        ai_service=ai_service,
        storage_path=str(parquet_path),
        file_name=f"{scenario.dataset_id} cleaned.parquet",
        analysis_id=scenario.dataset_id,
        upload_context=upload_context,
    )

    truth_text = truth_for_judge(truth)
    records = []
    for rec in computed["recommendations"]:
        source = rec.get("confidence_source") or "unknown"
        judge_label = None
        if judge_client is not None:
            judge_label = await judge_recommendation(judge_client, judge_model, rec, truth_text)
        if source.startswith("rule:"):
            label = label_rule_recommendation(rec, truth=truth, computed=computed)
        else:
            label = judge_label or Label(None, "No judge on this run.", "none")
        records.append(
            {
                "source": source,
                "confidence": rec.get("confidence"),
                "confidence_method": rec.get("confidence_method"),
                # Everything the judge saw, so any verdict can be re-audited.
                "title": rec.get("title"),
                "problem": rec.get("problem"),
                "evidence": rec.get("evidence"),
                "expected_impact": rec.get("expected_impact"),
                "description": rec.get("description"),
                "label": label.to_dict(),
                "judge_label": judge_label.to_dict() if judge_label else None,
            }
        )

    ai_result = computed["ai_result"]
    return {
        "dataset_id": scenario.dataset_id,
        "scenario": scenario.describe(),
        "truth": truth,
        "ai_recommendation_count": sum(r["source"].startswith("ai:") for r in records),
        # When both OpenAI calls fail, generate_analysis hands back the
        # deterministic list itself as its "recommendations".
        "ai_failed": ai_result.get("recommendations") is computed["deterministic_recommendations"],
        "executive_summary": ai_result.get("executive_summary", ""),
        "forecasts": [
            {k: f.get(k) for k in ("metric", "latest_value", "change_percent_next_month", "confidence")}
            for f in computed["forecasts"]
        ],
        "anomalies": [
            {k: a.get(k) for k in ("type", "column", "score", "period", "description")}
            for a in computed["anomalies"]
        ],
        "quality_issues": computed["statistics"]["data_quality"].get("issues", []),
        "recommendations": records,
    }


# ── Aggregation ─────────────────────────────────────────────────────────────


def summarize(raw_results: list[dict[str, Any]], run_info: dict[str, Any]) -> dict[str, Any]:
    from evals.calibration.metrics import (
        Scored,
        brier_score,
        expected_calibration_error,
        reliability_table,
        summarize_by_source,
    )

    scored: list[Scored] = []
    not_scored: Counter[str] = Counter()
    agreement: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "agree": 0})
    by_scenario: dict[str, list[Scored]] = defaultdict(list)
    recall: dict[str, dict[str, int]] = {
        "anomaly": {"planted": 0, "found_by_rules": 0, "found_by_ai": 0},
        "data_defect": {"planted": 0, "found_by_rules": 0, "found_by_ai": 0},
    }

    for result in raw_results:
        scenario = result["scenario"]
        found = {"anomaly": {"rules": False, "ai": False}, "data_defect": {"rules": False, "ai": False}}
        for record in result["recommendations"]:
            label, judge = record["label"], record.get("judge_label")
            if label["correct"] is None:
                not_scored[record["source"]] += 1
            else:
                item = Scored(result["dataset_id"], record["source"], float(record["confidence"]), label["correct"])
                scored.append(item)
                for key in (
                    f"grain={scenario['grain']}",
                    f"noise={'high' if scenario['noise'] >= 0.2 else 'low'}",
                    f"planted_anomaly={scenario['plant_anomaly']}",
                    f"optional_sparse_column={scenario['optional_sparse']}",
                ):
                    by_scenario[key].append(item)
            if record["source"].startswith("rule:") and judge and judge["correct"] is not None:
                if label["correct"] is not None:
                    for key in ("all", record["source"]):
                        agreement[key]["n"] += 1
                        agreement[key]["agree"] += judge["correct"] == label["correct"]
            if label["correct"]:
                family = "rules" if record["source"].startswith("rule:") else "ai"
                if record["source"] == "rule:anomaly" or label.get("planted_finding") == "anomaly":
                    found["anomaly"][family] = True
                if record["source"] == "rule:data_quality" or label.get("planted_finding") == "data_defect":
                    found["data_defect"][family] = True
        for finding, flag in (("anomaly", "plant_anomaly"), ("data_defect", "tracking_outage")):
            if scenario[flag]:
                recall[finding]["planted"] += 1
                recall[finding]["found_by_rules"] += found[finding]["rules"]
                recall[finding]["found_by_ai"] += found[finding]["ai"]

    return {
        **run_info,
        "datasets": len(raw_results),
        "datasets_with_ai_recommendations": sum(1 for r in raw_results if r["ai_recommendation_count"]),
        "datasets_where_ai_failed": [
            r["dataset_id"]
            for r in raw_results
            if r.get("ai_failed", not r["ai_recommendation_count"]) and run_info.get("ai_enabled")
        ],
        "scored_recommendations": len(scored),
        "not_scored_by_source": dict(sorted(not_scored.items())),
        "by_source": summarize_by_source(scored),
        "overall": {
            "brier_shown": _round(brier_score(scored)),
            "ece_shown": _round(expected_calibration_error(scored)),
            "reliability": reliability_table(scored),
        },
        "by_scenario": {
            key: summarize_by_source(items) for key, items in sorted(by_scenario.items())
        },
        "recall": recall,
        "judge_agreement_with_rule_labels": {
            key: {**counts, "rate": _round(counts["agree"] / counts["n"]) if counts["n"] else None}
            for key, counts in sorted(agreement.items())
        },
    }


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Confidence calibration — benchmark results",
        "",
        f"Generated {summary['generated_at']} · benchmark `{summary['benchmark_version']}` · "
        f"{summary['datasets']} datasets · analysis model `{summary.get('analysis_model')}` · "
        f"judge `{summary.get('judge_model')}`",
        "",
        "Produced by `python -m evals.calibration.run_eval` — do not edit by hand. "
        "Method and caveats: `docs/analytics/10_Confidence_Calibration.md`.",
        "",
        "## Per source",
        "",
        "| Source | n | Datasets | Confidence shown | Hit rate (95% CI) | Brier shown | Brier recalibrated (LOO) | Recalibrated confidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for source, row in summary["by_source"].items():
        low, high = row["hit_rate_95ci"]
        lines.append(
            f"| `{source}` | {row['n']} | {row['datasets']} | {row['mean_confidence_shown']:.2f} | "
            f"{row['hit_rate']:.2f} ({low:.2f}–{high:.2f}) | {row['brier_shown']:.3f} | "
            f"{row['brier_recalibrated_loo']:.3f} | {row['recalibrated_confidence']:.2f} |"
        )
    overall = summary["overall"]
    lines += [
        "",
        f"All scored recommendations: n={summary['scored_recommendations']}, "
        f"Brier {overall['brier_shown']}, ECE {overall['ece_shown']}. "
        f"Not scored (unverifiable / no ground truth): {summary['not_scored_by_source'] or 'none'}.",
        "",
        "## Reliability (all sources, confidence as shown)",
        "",
        "| Confidence bin | n | Mean confidence | Hit rate |",
        "|---|---|---|---|",
    ]
    for row in overall["reliability"]:
        if row["n"]:
            lines.append(
                f"| {row['bin']} | {row['n']} | {row['mean_confidence']:.2f} | {row['hit_rate']:.2f} |"
            )
    lines += [
        "",
        "## Recall on planted findings",
        "",
        "| Finding | Planted in | Found by rules | Found by AI |",
        "|---|---|---|---|",
    ]
    ai_enabled = bool(summary.get("ai_enabled"))
    for finding, row in summary["recall"].items():
        found_by_ai = row["found_by_ai"] if ai_enabled else "— (offline run)"
        lines.append(f"| {finding} | {row['planted']} | {row['found_by_rules']} | {found_by_ai} |")
    lines += ["", "## Judge check", ""]
    if ai_enabled:
        lines += [
            "The LLM judge also graded every rule-based recommendation, where deterministic "
            "labels exist. Agreement with those labels:",
            "",
            "| Rule source | Agree / n | Rate |",
            "|---|---|---|",
        ]
        for key, row in summary["judge_agreement_with_rule_labels"].items():
            lines.append(f"| {key} | {row['agree']}/{row['n']} | {row['rate']} |")
        failed = summary["datasets_where_ai_failed"]
        lines += [
            "",
            f"Datasets where the AI call failed (deterministic fallback used, so no AI "
            f"recommendations to score): {len(failed)} — {', '.join(failed) if failed else 'none'}.",
        ]
    else:
        lines.append(
            "Not run: this was an offline (`--no-ai`) run, so there are no AI recommendations "
            "and no judge. Rule-based recommendations are labeled deterministically."
        )
    lines += [
        "",
        "## By scenario",
        "",
        "| Slice | Source | n | Confidence shown | Hit rate |",
        "|---|---|---|---|---|",
    ]
    for slice_name, sources in summary["by_scenario"].items():
        for source, row in sources.items():
            lines.append(
                f"| {slice_name} | `{source}` | {row['n']} | {row['mean_confidence_shown']:.2f} | "
                f"{row['hit_rate']:.2f} |"
            )
    return "\n".join(lines) + "\n"


def calibration_table(summary: dict[str, Any]) -> dict[str, Any]:
    from app.analytics.calibration import MIN_SAMPLES, RULE_TRACKING

    sources = {
        source: {
            "confidence": row["recalibrated_confidence"],
            "n": row["n"],
            "hit_rate": row["hit_rate"],
            "hit_rate_95ci": row["hit_rate_95ci"],
            "confidence_before": row["mean_confidence_shown"],
            "brier_before": row["brier_shown"],
            "brier_after_loo": row["brier_recalibrated_loo"],
        }
        for source, row in summary["by_source"].items()
        if row["n"] >= MIN_SAMPLES and source != RULE_TRACKING
    }
    return {
        "description": (
            "Benchmark-measured confidence per recommendation source. Regenerated by "
            "`python -m evals.calibration.run_eval --write-table` (run from backend/). Sources "
            "absent here, or with n below MIN_SAMPLES in app/analytics/calibration.py, fall back "
            "to their hand-set defaults."
        ),
        "generated_at": summary["generated_at"],
        "benchmark": {
            "version": summary["benchmark_version"],
            "datasets": summary["datasets"],
            "analysis_model": summary.get("analysis_model"),
            "judge_model": summary.get("judge_model"),
        },
        "sources": sources,
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


# ── Entry point ─────────────────────────────────────────────────────────────


def _needs_retry(result: dict[str, Any]) -> bool:
    """The AI call or any judge call failed (usually a 429 rate limit)."""
    from evals.calibration.labels import JUDGE_FAILED_PREFIX

    judge_failed = any(
        (record.get(key) or {}).get("reason", "").startswith(JUDGE_FAILED_PREFIX)
        for record in result["recommendations"]
        for key in ("label", "judge_label")
    )
    return bool(result.get("ai_failed")) or judge_failed


async def _rejudge(args: argparse.Namespace) -> None:
    """Re-grade every saved recommendation with the current judge prompt and a
    freshly generated ground truth, without re-running the pipeline."""
    from openai import AsyncOpenAI

    from app.core.config import settings
    from evals.calibration.benchmark import draw_scenarios, write_dataset
    from evals.calibration.labels import judge_recommendation, truth_for_judge

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    scenarios = {s.dataset_id: s for s in draw_scenarios(args.datasets, seed=args.seed)}
    semaphore = asyncio.Semaphore(args.concurrency)

    async def one(path: Path) -> None:
        result = json.loads(path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            _, truth = write_dataset(scenarios[result["dataset_id"]], Path(tmp))
        truth_text = truth_for_judge(truth)
        for record in result["recommendations"]:
            async with semaphore:
                label = await judge_recommendation(client, args.judge_model, record, truth_text)
            record["judge_label"] = label.to_dict()
            if not record["source"].startswith("rule:"):
                record["label"] = label.to_dict()
        result["truth"] = truth
        path.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
        print(f"re-judged {result['dataset_id']}", file=sys.stderr)

    await asyncio.gather(*(one(p) for p in sorted((RESULTS_DIR / "raw").glob("*.json"))))


def _load_raw_results() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((RESULTS_DIR / "raw").glob("*.json"))
    ]


async def _run(args: argparse.Namespace) -> None:
    from app.core.config import settings
    from evals.calibration.benchmark import draw_scenarios

    scenarios = draw_scenarios(args.datasets, seed=args.seed)
    raw_dir = RESULTS_DIR / "raw"
    if args.retry_failed:
        failed = {r["dataset_id"] for r in _load_raw_results() if _needs_retry(r)}
        scenarios = [s for s in scenarios if s.dataset_id in failed]
        print(f"Retrying {len(scenarios)} datasets with failed AI or judge calls", file=sys.stderr)
    elif raw_dir.exists():
        for stale in raw_dir.glob("*.json"):
            stale.unlink()
    if args.no_ai:
        ai_service, judge_client = _OfflineAIService(), None
    else:
        from openai import AsyncOpenAI

        from app.services.ai_service import AIService

        ai_service, judge_client = AIService(), AsyncOpenAI(api_key=settings.openai_api_key)

    raw_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(args.concurrency)
    started = time.monotonic()

    async def one(scenario: Any) -> None:
        async with semaphore:
            for attempt in range(args.retries + 1):
                with tempfile.TemporaryDirectory() as tmp:
                    result = await run_dataset(
                        scenario,
                        Path(tmp),
                        ai_service=ai_service,
                        judge_client=judge_client,
                        judge_model=args.judge_model,
                    )
                if args.no_ai or not _needs_retry(result) or attempt == args.retries:
                    break
                wait = 60 * (attempt + 1)
                print(f"{scenario.dataset_id}: AI/judge call failed; retrying in {wait}s", file=sys.stderr)
                await asyncio.sleep(wait)
            (raw_dir / f"{scenario.dataset_id}.json").write_text(
                json.dumps(result, indent=1, default=str), encoding="utf-8"
            )
            print(
                f"[{time.monotonic() - started:6.0f}s] {scenario.dataset_id}: "
                f"{len(result['recommendations'])} recommendations"
                f"{' (still failing)' if _needs_retry(result) and not args.no_ai else ''}",
                file=sys.stderr,
            )

    await asyncio.gather(*(one(s) for s in scenarios))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", type=int, default=48)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--no-ai", action="store_true", help="Offline run: rule-based recommendations only")
    parser.add_argument("--judge-model", default=None, help="Defaults to the analysis model")
    parser.add_argument("--rescore", action="store_true", help="Recompute metrics from saved raw results")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Re-run only datasets whose AI or judge calls failed, then re-summarize",
    )
    parser.add_argument("--retries", type=int, default=2, help="Per-dataset retries on AI/judge failure")
    parser.add_argument(
        "--rejudge",
        action="store_true",
        help="Re-grade saved recommendations with the current judge prompt (judge calls only)",
    )
    parser.add_argument("--write-table", action="store_true", help="Update app/analytics/calibration_table.json")
    args = parser.parse_args()

    _bootstrap_env(no_ai=args.no_ai or (args.rescore and not (args.retry_failed or args.rejudge)))
    from app.core.config import settings
    from evals.calibration.benchmark import BENCHMARK_VERSION, DEFAULT_SEED

    args.seed = DEFAULT_SEED if args.seed is None else args.seed
    args.judge_model = args.judge_model or settings.openai_model

    if args.rescore or args.retry_failed or args.rejudge:
        if args.rejudge:
            asyncio.run(_rejudge(args))
        if args.retry_failed:
            asyncio.run(_run(args))
        previous = json.loads((RESULTS_DIR / "summary.json").read_text(encoding="utf-8"))
        run_info = {key: previous.get(key) for key in ("generated_at", "benchmark_version", "analysis_model", "judge_model", "ai_enabled", "seed")}
    else:
        asyncio.run(_run(args))
        run_info = {
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "benchmark_version": BENCHMARK_VERSION,
            "seed": args.seed,
            "ai_enabled": not args.no_ai,
            "analysis_model": None if args.no_ai else settings.openai_model,
            "judge_model": None if args.no_ai else args.judge_model,
        }

    summary = summarize(_load_raw_results(), run_info)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (RESULTS_DIR / "REPORT.md").write_text(render_report(summary), encoding="utf-8")
    print(render_report(summary))

    if args.write_table:
        from app.analytics.calibration import CALIBRATION_TABLE_PATH

        CALIBRATION_TABLE_PATH.write_text(
            json.dumps(calibration_table(summary), indent=2) + "\n", encoding="utf-8"
        )
        print(f"Wrote {CALIBRATION_TABLE_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
