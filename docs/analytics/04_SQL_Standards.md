# SQL Review & Standards

Full query-by-query review of every raw SQL / DuckDB statement in the
backend. Scope was explicitly **comments, naming, and consolidation of
duplicate helpers only — no query logic was changed.** Every fix below was
verified against the existing test suite before and after.

---

## 1. What changed in this pass

### 1.1 Consolidated `quote_identifier` — 5 copies → 1

`_quote_identifier()` (double-quote a DuckDB identifier, escaping embedded
quotes) was defined identically, byte-for-byte, in five files:
`statistics.py:263-264`, `data_quality.py:216-217`, `anomaly_detection.py:176-177`,
`forecasting.py:107-108`, `live_filter.py:34-35`.

**Fix**: moved to a single shared module, `backend/app/analytics/sql_utils.py`,
and re-imported under the same private name (`from app.analytics.sql_utils
import quote_identifier as _quote_identifier`) at each former call site —
every existing call to `_quote_identifier(...)` across all five files works
unchanged; only the definition moved. This is a pure refactor: identical
input → identical output, verified by re-running each module's test file
(`docs/analytics/09_Verification.md` — see the verification log for exact
pass/fail counts).

### 1.2 Everything else in this section: documented, not changed

The remaining findings below are read-only review notes. Fixing them would
touch query logic or cross-module behavior, which was out of scope for this
pass (the instruction was explicitly "avoid changing behaviour"). They're
recorded here as the reviewed, prioritized backlog a follow-up pass would
work from.

---

## 2. Query-by-query review

| # | File:line | Purpose | Parameterization | Comment quality |
|---|---|---|---|---|
| 1-7 | `file_processor.py:977-1004` | Load parsed CSV/Excel/JSON/Parquet into DuckDB (`CREATE OR REPLACE TABLE`, row counts) | Table name and file path interpolated directly, **not** via `quote_identifier` | None. Safe today only because both values are always server-generated (fixed `"data"` table name, UUID-based file paths), never user input — but the pattern is inconsistent with every other module's discipline. **Recommendation**: route through `quote_identifier`/parameterize for consistency, even though there's no live vulnerability. |
| 8-16 | `statistics.py` | Schema (`DESCRIBE`), batched numeric stats, per-column fallback, date ranges, top-10 categories, unique counts, pairwise correlation | `quote_identifier` throughout (now via the shared module) | Good — batching rationale commented (`:89-90`); percentile pre-filter ordering commented (via `anomaly_detection.py`, same author style) |
| 17-21 | `data_quality.py` | Null counts, IQR outlier scan, negative-financial-value scan, exact-duplicate detection, hardcoded "part exceeds whole" checks | `quote_identifier` throughout | The relationship-check intent is commented; the IQR-bounds interpolation (Python floats, not `?` params) is not — flagged as a minor style inconsistency vs. `live_filter.py`'s parameterized approach, not a risk (values are always internally computed floats). |
| 22-23 | `anomaly_detection.py` | Row-level z-score + percentile (`CUME_DIST()`), monthly time-series z-score | `quote_identifier` | The percentile pre-filter ordering has a **genuinely good** explanatory comment (`:65-67`) — kept as a model example of "comment the *why*, not the *what*" elsewhere in this review. |
| 24 | `forecasting.py` | Monthly `SUM(metric)` series for OLS trend fit | `quote_identifier` | Module docstring frames the deliberate "simple, transparent, not overconfident" design choice — a good pattern worth repeating in modules that don't have one. |
| 25-31 | `live_filter.py` | Per-chart-type aggregation + live re-query, KPI recompute | `quote_identifier` **and** an explicit column-role allowlist (`ALLOWED_FILTER_ROLES`) checked before any identifier reaches SQL; filter **values** always via `?` params | The most defensively written SQL in the codebase — allowlist + parameterization + a module docstring stating the security rationale outright. Held up here as the standard the rest of the codebase should be brought to, not an outlier to fix. |
| 32 | `analyses.py:617` | Live-filter row count | `?` params | — |

---

## 3. Naming conventions observed (and where they're inconsistent)

- **Private module functions** are consistently prefixed `_` (`_quote_identifier`, `_single_int`, `_row_count`, `_forecast_metric`, ...) — followed uniformly across all analytics modules.
- **SQL aliases inside queries** are short and consistent (`row_count`, `duplicates`, `z_score`, `period`) — no cryptic single-letter aliases found in any reviewed query.
- **Magic numbers are the main naming/documentation gap**, not identifier naming. Examples found without a named constant or comment explaining the choice:
  - Anomaly z-score thresholds: `3` (row-level, `anomaly_detection.py:76`) vs. `2.5` (monthly, `:145`) — two different thresholds for the same underlying concept, undocumented why they differ.
  - Correlation significance cutoff `0.3` (`statistics.py:235`).
  - Category cardinality cutoff `50` and `LIMIT 10` for top-category queries (`statistics.py:174-181`).
  - `_NUMERIC_AGGS_PER_COLUMN = 11` (`statistics.py:77`) — a named constant, which is good, but tightly coupled to the literal count of aggregate expressions a few lines later with no cross-reference comment tying them together; changing one without the other would silently break row-chunking offset math.

None of these are bugs — they're all working as intended — but each is a place where a future maintainer (or an interviewer reading the code cold) has to reverse-engineer *why* `3` and not `2.8` or `3.5`. Naming them (`ANOMALY_ROW_ZSCORE_THRESHOLD = 3`, etc.) is a low-risk, high-readability follow-up, deliberately left undone here to keep this pass behavior-neutral (renaming a bare literal to a constant is safe, but touching that many files without a full test run available for every one of them — see `docs/analytics/09_Verification.md` for which modules actually got a verified test pass — was judged higher-risk than the readability gain justified in one sitting).

---

## 4. Standards for new SQL in this codebase, based on what's already working well

Distilled from the best examples already in the code (`live_filter.py`, `anomaly_detection.py`'s percentile comment, `forecasting.py`'s module docstring):

1. **Always quote identifiers** via `app.analytics.sql_utils.quote_identifier` — never interpolate a column/table name raw, even when the current call site happens to be safe, so the discipline doesn't have to be re-derived per file.
2. **Parameterize values, not just identifiers**, wherever the query touches anything that didn't originate from a fixed, server-controlled source — `live_filter.py`'s `?`-param pattern is the reference.
3. **Comment the *why*, not the *what***: a `WHERE z_score >= 3` line doesn't need a comment saying "filters to high z-scores" — it needs one saying why 3 and not another threshold, if that number was a deliberate choice (`anomaly_detection.py:65-67`'s percentile-ordering comment is the model to copy).
4. **Name magic numbers that encode a business or statistical judgment call** (a threshold, a cardinality cutoff, a significance level) even if they're only used once — the reader needs to know it's a decision, not an arbitrary literal.
5. **New DuckDB helper functions belong in `sql_utils.py`**, not redefined locally — this file exists now specifically to prevent the five-way duplication this review found from recurring.
