# Analytics Portfolio Report — Zephyr (AI Dashboard Generator)

> Self-assessment produced as part of a documentation and code-quality
> review targeted at Senior Data Analyst / Analytics Engineer / AI Data
> Analyst roles (OpenAI, NVIDIA, Capita, NHS, Microsoft, Amazon, and AI
> startups). Scope was explicit: **no application behavior was changed.**
> Everything below is either newly written documentation, a new additive
> module, or a small number of behavior-preserving refactors — see
> [`docs/analytics/09_Verification.md`](docs/analytics/09_Verification.md)
> for exactly what was and wasn't verified, and why.
>
> Scores are self-assessed and calibrated deliberately conservatively —
> a score with no supporting gap analysis next to it isn't credible to the
> technical reviewers this document is written for. Every score below is
> followed by the evidence for it and the specific gaps holding it back
> from higher.

---

## Scores

| Dimension | Score | Summary |
|---|---|---|
| Analytics maturity | **78 / 100** | Real deterministic-first architecture, statistically grounded forecasting/anomaly detection, and a genuine data-quality framework — held back by uncalibrated confidence scores and three cross-module business-rule inconsistencies |
| SQL quality | **74 / 100** | Consistent identifier quoting, one module (`live_filter.py`) with best-practice parameterization + allowlisting — held back by undocumented magic numbers and one now-fixed but previously 5×-duplicated helper |
| Data engineering | **80 / 100** | A real, ordered ETL pipeline with explicit sync/async boundaries, deterministic cleaning, and graceful multi-tier AI fallback — held back by no working local dev environment out of the box and zero test coverage on the AI service layer |
| Data modelling | **76 / 100** | Clean 3NF Postgres schema, correct cascade behavior, defensible JSONB denormalization — held back by two missing indexes, one model/migration drift, and no ENUM/CHECK constraints |
| Documentation | **90 / 100** | Nine new analytics documents, all cited to file:line, an honest known-gaps section, and a worked business-insights example on real computed numbers — this is the dimension this review most directly improved |
| Business impact / product thinking | **82 / 100** | A specified (not hand-waved) executive dashboard that identifies exactly which of 20+ KPIs are computable today vs. schema-blocked, and a business-insights worked example that ends in prioritized, evidence-backed recommendations |
| Recruiter impression | **83 / 100** | The single strongest signal in this repo for a technical interviewer is that it documents its own real gaps with the same rigor it documents its strengths — see [§6](#6-why-honest-gaps-are-the-actual-portfolio-asset-here) |

**Composite: 80/100** (unweighted mean). Read as: a genuinely strong, real engineering artifact with specific, fixable, well-understood gaps — not a finished, production-hardened system, and this document doesn't pretend otherwise.

---

## 1. Analytics maturity — 78/100

**Evidence for the score:**
- Statistics, KPI detection, forecasting, and anomaly detection all run *before* any AI call — a deliberate, correctly-implemented architectural decision (`docs/analytics/01_Data_Architecture.md`), not an accident of ordering.
- Forecast confidence is a real formula (history length × residual noise), not a placeholder (`docs/analytics/03_Analytics_Glossary.md §4`).
- A real data quality framework exists at two levels — a pipeline-integrated detector and a new standalone, tested, reusable toolkit (`docs/analytics/02_Data_Quality_Framework.md`).

**What holds it back:**
- KPI tiles and charts disagree on sum-vs-average aggregation for the same column on certain naming patterns (`docs/analytics/01_Data_Architecture.md §8`) — a real correctness bug, documented but not fixed in this pass (fixing it changes displayed numbers, which was explicitly out of scope).
- Confidence scores are six different, non-interchangeable things across the codebase, and the most user-visible one (AI recommendation confidence) is a fixed lookup table, not a calibrated measure (`docs/analytics/08_AI_Analytics_and_Guardrails.md §6`). *(Follow-up, 2026-09-11: rule-based recommendation confidence is now measured — see §8, item 3.)*
- Currency/percentage/aggregation-type detection is independently reimplemented 3× with drifting keyword lists.

---

## 2. SQL quality — 74/100

**Evidence:**
- Every DuckDB query quotes identifiers; `live_filter.py` additionally validates column *roles* against an explicit allowlist before any identifier reaches SQL, and parameterizes every filter value.
- Fixed in this pass: `quote_identifier` was defined identically five times across five files — consolidated into `backend/app/analytics/sql_utils.py`, a pure, verified refactor (`docs/analytics/04_SQL_Standards.md §1`).

**What holds it back:**
- Several statistically/business-meaningful thresholds are bare literals with no named constant or comment (anomaly z-score thresholds of `3` vs `2.5` for two different checks, correlation significance `0.3`, category cardinality `50`) — flagged, not fixed, to keep this pass to comments/consolidation only, even though the full suite (see below) now runs clean and *could* support touching them safely.
- `file_processor.py`'s DuckDB load queries interpolate file paths/table names without the shared quoting helper — safe today only because those values are always server-generated, not a defended pattern.

**Verification**: the `sql_utils.py` consolidation is confirmed safe against the full 112-test suite, not just the modules that were quick to isolate — see `docs/analytics/09_Verification.md §3`.

---

## 3. Data engineering — 80/100

**Evidence:**
- A real, traceable pipeline with an explicit sync/async boundary (cleaning happens in the request; the Celery task only orchestrates statistics → AI) — correctly documented and, notably, easy to get backwards, which is exactly why it's worth documenting precisely (`docs/analytics/01_Data_Architecture.md §2`).
- A three-tier AI fallback (Responses API → Chat Completions → fully deterministic template) that degrades gracefully under failure instead of forcing a response.
- Real rate limiting (`slowapi`, per-route limits from config, not hardcoded), real JWT verification (JWKS + HS256, fail-closed by design, tested with actual signed tokens — not mocked).

**What holds it back:**
- **`requirements.txt`'s pinned versions are incompatible with current Python (3.14): no wheel exists for several packages at their pinned versions (`pydantic-core`, `duckdb`, `pyarrow`, `asyncpg`, `Pillow`), and `pydantic-core`'s Rust extension refuses to build at all against 3.14 (PyO3 0.24.1 tops out at 3.12/3.13).** Diagnosed in full in `docs/analytics/09_Verification.md §2`, including the follow-on discovery that `app/core/config.py` instantiates `Settings()` at *import time*, so `pytest` can't even collect tests without required env vars already set — and `conftest.py`'s fixture sets them too late (test-execution time, not collection time) to help, while `backend/.env` doesn't exist at all. This is a real, fixable onboarding/CI gap with a precise root cause, not a vague "works on my machine" complaint.
- **Once resolved, the full suite runs clean — 112 passed, 0 failed** (92 pre-existing + 20 new), which is itself evidence the underlying pipeline logic is sound; the friction was entirely in getting the environment to a runnable state, not in the code once it ran.
- `ai_service.py` — the most consequential file in the AI-safety story — had **zero test coverage** at the time of this review; a prior test file covering it (`test_ai_service_chat_context.py`) exists in git history but was deleted with nothing replacing it. *(Follow-up, 2026-09-11: addressed by `backend/tests/test_ai_service.py` — see §8, item 2.)*
- The live-filter endpoint re-reads and re-parses the entire source file from disk on every slicer click — no caching, a real (if minor at current scale) performance gap.
- A fully-built, fail-closed sandboxed-code-execution module exists and is completely unwired into the pipeline — not a bug, but worth an engineer noticing rather than assuming it's live.

---

## 4. Data modelling — 76/100

**Evidence:**
- Clean 3NF PostgreSQL schema, 7 tables at the time of this review (8 since the 2026-09-11 `recommendation_feedback` table), no many-to-many sprawl, correct `ON DELETE CASCADE` on every foreign key — the one later exception, `recommendation_feedback.insight_id ON DELETE SET NULL`, is deliberate — and deliberate (not accidental) JSONB denormalization for genuinely semi-structured output (`docs/analytics/05_Data_Modelling.md §4`).
- A proposed dimensional model for a realistic future requirement (cross-analysis reporting) is included and explicitly labeled as a proposal, not a description of what's built — the discipline of not overclaiming architecture is itself part of what's being scored here.

**What holds it back:**
- `analyses.file_id` (a foreign key used in real query paths) has no index.
- `subscriptions.user_id` has a documented model/migration drift — the ORM model declares an explicit index the migration never creates.
- No DB-level `ENUM`/`CHECK` constraints anywhere — `status`, `plan`, and `role` columns are all app-enforced-only `VARCHAR`.

---

## 5. Documentation — 90/100

**Evidence:** nine new documents (`docs/analytics/01`–`09`), a rewritten recruiter-facing README that links every one of them, and a business-insights document whose numbers were independently recomputed from the raw CSV rather than copy-pasted from the app's own output — a genuine independent-verification exercise, not just narration. Every non-obvious technical claim across all nine documents cites a `file:line`.

**What holds it back from higher:** no architecture-decision-record (ADR) history exists for *why* past decisions were made (only what they are today), and there are no auto-generated docs (e.g. OpenAPI-derived endpoint reference, docstring-extracted API docs) — everything here was hand-written this pass, which is a real one-time cost for a project of this size to keep current going forward.

---

## 6. Why honest gaps are the actual portfolio asset here

A portfolio that only documents what works reads, to any technical interviewer, as either an early-stage project or an incomplete review. Every document in `docs/analytics/` pairs what's real with what isn't, using the same rigor for both — the KPI/chart aggregation mismatch, the uncalibrated confidence scores, the missing indexes, the untested AI service, the dependency-install friction this review had to diagnose and route around before it could produce the 112-passed result cited throughout this report. None of these were hidden or softened. That's a deliberate choice, not an oversight: a Senior/Staff-level reviewer evaluating this repo will find the gaps whether or not this document names them, and naming them first — with the root cause, not just the symptom — is the stronger signal.

---

## 7. ATS keyword coverage

Checked against a representative keyword set for Senior Data Analyst / Analytics Engineer / AI Data Analyst postings at companies like the ones named in this review's brief:

| Keyword / phrase | Present in repo | Where |
|---|---|---|
| ETL / data pipeline | ✅ | `docs/analytics/01_Data_Architecture.md` |
| Data quality / data validation | ✅ | `docs/analytics/02_Data_Quality_Framework.md`, `data_quality_checks.py` |
| KPI / metrics / business definitions | ✅ | `docs/analytics/03_Analytics_Glossary.md` |
| SQL / query optimization | ✅ | `docs/analytics/04_SQL_Standards.md` |
| Data modelling / ER diagram / normalization | ✅ | `docs/analytics/05_Data_Modelling.md` |
| Dashboard / executive reporting | ✅ | `docs/analytics/06_Dashboard_Specification.md` |
| Business insights / stakeholder communication | ✅ | `docs/analytics/07_Business_Insights.md` |
| AI / LLM / hallucination prevention / prompt engineering | ✅ | `docs/analytics/08_AI_Analytics_and_Guardrails.md` |
| Forecasting | ✅ | `analytics/forecasting.py`, glossary §4 |
| Anomaly detection | ✅ | `analytics/anomaly_detection.py`, glossary §5 |
| Data governance / security | ✅ | JWT verification, rate limiting, sanitization — `08_AI_Analytics_and_Guardrails.md §4` |
| Testing / test coverage | ✅ | `09_Verification.md` — 112 passed, 0 failed (92 pre-existing + 20 new); 179 passed, 0 failed after the 2026-09-11 `ai_service.py` follow-up |
| Star schema / dimensional modelling | ✅ | `05_Data_Modelling.md §6` (proposed, clearly labeled) |
| Python / SQL / FastAPI / PostgreSQL / DuckDB | ✅ | throughout |
| CI/CD | ⚠️ Partial | `.github/workflows/` exists; not exercised or reviewed as part of this pass |
| A/B testing / experimentation | ❌ | Not present anywhere in this codebase — genuinely out of scope for what this product does |
| dbt / Airflow / orchestration tooling | ❌ | Not used — this system's "orchestration" is Celery, which is documented, but dbt/Airflow-specific keyword matches won't fire |

**Coverage: 12/15 core terms present and substantively documented (80%)**, with the two clean misses (A/B testing, dbt/Airflow) being genuine scope mismatches rather than gaps to backfill artificially — adding a dbt project to a system with no data warehouse would be worse portfolio signal, not better.

---

## 8. Recommendations for a top-1% AI Data Analyst portfolio

In priority order, each tied to a specific, already-identified gap rather than generic advice:

1. ✅ *Done 2026-09-11 — `scipy` dropped, `backend/.python-version` pins 3.12, and `conftest.py` seeds safe test env vars at import time so `pytest` collects from a clean clone with nothing exported (see `09_Verification.md §5`).* **Fix the dependency-install story — root cause is now precisely known.** A recruiter or interviewer who tries `git clone && pip install -r requirements.txt && pytest` on a machine with Python 3.14 will hit the exact wall this review diagnosed: `pydantic-core`'s pinned version won't build (PyO3 doesn't support 3.14 yet), which aborts the whole batch install, and even once dependencies are in place, `pytest` can't collect tests without `backend/.env` or exported env vars, because `app/core/config.py` builds `Settings()` at import time while `conftest.py`'s env fixture only runs at test-execution time. Three concrete fixes, in order of effort: drop unused `scipy`; add a `.python-version` pinning 3.12/3.13 (matching the Dockerfile's own `python:3.12-slim`) so contributors get a clear signal before hitting a build log; ship a committed `backend/.env.test` (safe dummy values only) that `pytest`'s config loads automatically. Full diagnosis: `docs/analytics/09_Verification.md §2`.
2. ✅ *Done 2026-09-11 — `backend/tests/test_ai_service.py` covers response parsing, chart sanitization, recommendation normalization, the full LLM fallback chain, and chat grounding against a fake client. Writing it surfaced two real bugs, both fixed with regression tests: the chart safety filter's `"nan"` substring check silently dropped charts labelled e.g. "Finance" or "Maintenance" (now whole-token / JS-syntax matching), and `_parse_financial_opportunity("$1.5M")` returned `1.5` (now honours K/M/B and thousand/million/billion suffixes).* **Add coverage for `ai_service.py`.** This is the single file every AI-safety claim in `docs/analytics/08_AI_Analytics_and_Guardrails.md` rests on, and it currently has none — a gap made more notable by the fact that it *used to* have some (`test_ai_service_chat_context.py`, deleted with nothing replacing it).
3. ◐ *Partly done 2026-09-11 — a planted-truth benchmark (`backend/evals/calibration/`) runs 48 synthetic datasets through the production pipeline, with held-back months for forecasts and an LLM judge checked against deterministic labels. It found every rule source overconfident (forecasts 0.83 → 0.72, anomalies 0.78 → 0.49, data quality 0.90 → 0.49); those measured values now drive production via `calibration_table.json`. A production feedback loop (👍/👎 per recommendation, snapshotting the confidence shown, aggregated by a SQL view) is live. Still open: the AI tiers — the paid run was rate-limited and exposed a judge-prompt defect, so it was archived, not used. Details: `docs/analytics/10_Confidence_Calibration.md`.* **Build the calibration eval.** Log recommendation outcomes, build a small labeled benchmark, replace the fixed `{High: 0.85, Medium: 0.7, Low: 0.55}` lookup with a real, periodically-validated confidence score. Fully specified in `docs/analytics/08_AI_Analytics_and_Guardrails.md §6`.
4. ◐ *Partly done 2026-09-12, driven by a real upload (six UK government major-projects spreadsheets): currency is now detected from the original column headers (`£m`) instead of assumed USD, and the keyword vocabularies match whole words via `app/analytics/text_matching.py` — previously `"arr"` matched inside "n**arr**ative", typing narrative text columns as annual recurring revenue. The three lists themselves are still maintained separately, so the SUM/AVG drift below stands. Full diagnosis: `docs/analytics/09_Verification.md §8`.* **Resolve the SUM/AVG and currency-detection drift** identified in `docs/analytics/01_Data_Architecture.md §8` — three independently-maintained keyword lists for the same underlying classification is the highest-risk correctness issue in the codebase precisely because it's silent: nothing errors, numbers are just quietly inconsistent between a KPI tile and its own chart.
5. **Close the three schema gaps in `docs/analytics/06_Dashboard_Specification.md §2.10`** (plan-price lookup, `analyses.completed_at`, export/trial event logging) — small, well-scoped changes that would make the proposed executive dashboard fully buildable rather than 70% blocked.
6. **Add real screenshots and a recorded demo.** Explicitly skipped in this pass (`README.md`, "Screenshots" section) rather than faked — but it's genuine, easy, high-leverage portfolio value once a Supabase project and running stack are available.
7. **Publish the ER diagrams and the proposed dimensional model as an actual artifact** (this review generated Mermaid diagrams in-repo; rendering them as a shareable page or including them in a portfolio site would surface the modelling work to a reviewer who won't clone the repo).
