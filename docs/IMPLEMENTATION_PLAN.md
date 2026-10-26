# Zephyr upgrade: architecture and implementation plan

## Release reliability increment (16 October 2026)

Completed the first cross-dataset release gate: 16 known-answer runs cover
missing values, refunds, repeated records, identifiers, product codes, ratings,
optional notes and survey scope through production parsing/cleaning/analysis.
Tests also reverse source order to detect order-dependent loss. These cases run
in the existing pytest CI job. Safe default cleaning preserves missing amounts
and repeated transactions; category merging requires an explicit selection.
Website upload options match those defaults. Fresh-install migrations now create
their required UUID extension. The disposable database runner passes all 19
ownership, saved-metric, usage and feedback checks without touching app data.

Next release gates remain: representative AI-output evaluation; staging HTTPS,
persistent storage, tested backups and monitoring; production OAuth callbacks;
Android release/iOS device checks; and payment/quota lifecycle testing before
charging customers. These checks are not replaced by the offline benchmark.

## Recommendation and chat evidence increment (16 October 2026)

Descriptive record labels and weekly-sales context are implemented in the
website/app: date/region/category/channel replace generic primary entry numbers,
with file position retained separately. Reports explain the record meaning,
and range charts use the supported record type in titles, captions and counts.
Saved-schema checks prevent applying weekly-sales meaning to unrelated files.
Backend/database/client checks pass; Samsung review is complete. After a clean
Expo reload, the data explanation, specific chart title and descriptive record
heading were visible, with the analysed-file position retained separately.

Range-chart clarity is also implemented: horizontal readable ranges, visible
entry counts, measured summaries, explicit rounded/capped scope, matching filter
and export presentation, and clearing bars when a filter has no matches. The
revenue range chart was visually verified on the Samsung with all 12 ranges.

The next business-wording increment is implemented: comparisons lead with the
measured ranking/gap, recommendations name their saved field/value and a specific
source check, and forecasts show a baseline, possible range and planning guidance.
The presentation applies to existing audited replies and reports on read;
measurements and stored history remain unchanged. Offline QA covered the three
supplied files, with ownership, feedback and export regressions passing. New
Samsung wording QA is complete after reconnecting the phone: the ranking
headline/gap, forecast planning explanation and specific recommendation are
readable, with chat and recommendation links opening their matching entries.

User-facing wording follows [PRODUCT_LANGUAGE.md](PRODUCT_LANGUAGE.md): lead
with a concise business answer and retain formulas in internal evidence or
optional explanations. Chat deduplicates equivalent facts, preserves important
qualifications in plain language, and reformats older audited replies on read
without rewriting history or consuming an AI allowance.

The presentation layer now also covers saved report summaries, insights,
forecasts, recommendations and file checks, including shared reports and exports.
It preserves raw measurements and audit inputs, explains uncertainty in ordinary
language, and keeps scores/formulas in optional details. Website and Samsung
labels follow the same product voice. All four report areas and the optional
file-check disclosure were reviewed on the Samsung on 16 October.

Recommendations now expose a measured action catalogue. The model selects
existing IDs; the server preserves canonical evidence and actions, audits
rejected IDs/free-form attempts, and falls back to deterministic actions.
Chat and summary refresh share read-only saved-measurement reconstruction.
Chat renders selected measured statements with field, operation, count basis,
calculation and scope. Unknown IDs and unsupported questions are non-success
outcomes and do not consume the user's allowance. Existing recommendation cards
are unchanged until a full analysis refresh.

Chat now also supports typed, owner-scoped plans for filtered and grouped
calculations over uploaded data. The server validates field roles and filters,
executes parameterized calculations and renders the actual results; model-written
numbers are not accepted. Unsupported plans remain non-success outcomes.

Website and mobile now include Compare groups and paginated supporting-entry
views. File-check links use saved criteria; recommendation links and optional
figures use saved measurements. Direct comparisons and entry viewing require no
AI call or AI allowance. Links include a report revision, and entry counts must
reconcile before records are shown. Positions refer to the analysed copy, not
necessarily the original spreadsheet. Original blank cells cannot be located
after filling unless their positions were retained; no positions are invented.

iOS device verification remains outstanding; the connected device is the Samsung
Android phone.

## Audit (9 October 2026)

Zephyr is an existing Next.js/React/TypeScript web app plus an Expo mobile app,
backed by FastAPI, PostgreSQL, Redis/Celery, Supabase Auth, DuckDB and ECharts.
Uploads are profiled and optionally cleaned; a worker computes statistics, KPIs,
charts, forecasts and anomalies, then asks the configured OpenAI model for a
structured narrative. Analyses and chart JSON are saved in PostgreSQL. The
authenticated API owns saved analyses, uploads, filtered chart/KPI queries, chat
and exports. The app uses local/S3/Supabase storage configuration; the current
Docker deployment persists local uploads in a volume. Tests use pytest, Ruff,
TypeScript, ESLint and mobile smoke tests.

At the audit, the semantic detector and KPI rules inferred column roles and
aggregation, but users could not approve and reuse business definitions. Chart
JSON was saved without a separately versioned dashboard specification. Live
filtering recalculated charts and KPIs, but date filtering and calculation
provenance were limited. The delivered increments below address part of this;
model-driven chart creation and calculation edits are still pending.
Plan limits are static, counters are monthly fields without an authoritative
billing-period ledger, and Stripe IDs exist without a checkout/webhook lifecycle.
No payment flow should be represented as live.

## Implementation order

1. **Analytical foundation:** add owner-scoped, versioned metric definitions
   attached to uploaded datasets. Suggest only calculable SUM/AVG/COUNT/DISTINCT
   COUNT definitions, let owners approve or edit them, and execute approved
   definitions through a parameterized DuckDB query plan. Preserve existing
   dashboards and migrate safely. Include calculation and source provenance.
2. **Dashboard quality:** persist a validated versioned specification, add
   genuine date/category filters and transparent KPI/chart calculations, then
   improve comparisons and insight evidence. Reuse current ECharts components.
3. **Conversation:** split deterministic edits from model-driven requests; add
   validated targeted chart patches, undo and persistence. New calculations must
   use the approved query layer.
4. **Commercial controls:** reconcile the requested Free/Starter/Pro plans with
   existing `professional` records, add billing-period usage ledgers, atomic
   reservations and idempotency, and enforce server-side entitlements. Introduce
   Stripe code only with verified webhooks and explicit product/price setup.
5. **Release hardening:** run cross-account, quota, migration, mobile and build
   checks; configure durable storage, payment credentials and production HTTPS;
   measure AI spend with provider usage and effective-date price tables.

### Summary evidence increment (15 October 2026)

Executive summaries now use a catalogue of server-generated measured statements.
AI ranks known fact IDs; the server renders their fixed text and retains mandatory
scope and cleaning qualifications. Each selected fact carries its source field,
calculation, values and population. This avoids treating a number that appears
somewhere in the profile as proof of a different claim. Weighted values keep
their weighting, category percentages state their denominator, serial numbering
is excluded from entity coverage, and model-assisted labels cannot change the
meaning of a source measure.

Owners can update an older summary from its saved profile and KPI measurements
without running another analysis or consuming an AI request. The previous text
is retained for recovery; charts remain unchanged. Missing old weighting details
are not reconstructed by guessing, and analyses without saved profiles require
regeneration. Web/mobile disclosures show the selected calculations. Further
work is needed for semantic validation of recommendation prose and chat answers;
this increment does not establish external factual accuracy of supplied data.

This sequence preserves existing authentication, data and saved dashboards.
New API fields are additive; approved definitions do not silently rewrite old
analysis results. Recalculation is explicit and versioned.

Existing quotas count analysis creation and successful chat responses in mutable
user fields, and a scheduled task resets every account on the first of the
month. The requested Free lifetime allowance and paid billing-period limits
cannot safely be substituted into those fields. The commercial phase must
establish an event ledger, reconcile existing accounts, define failed/refunded
operation handling, and switch enforcement atomically before changing limits.
Chat responses now include model, token counts and an explicit success status
in saved internal metadata. A provider failure does not increment the current
AI-query counter. These corrections do not make the mutable counters an
authoritative usage ledger or establish monetary cost estimates.

Migration 007 now adds an idempotent operational usage ledger. It backfills
analysis rows with observed outcomes and older assistant messages with a
conservative `legacy_unknown` status when success cannot be proved. New analysis
requests reserve an event, worker completion/failure updates it, and chat replies
record their outcome, model and tokens. `/users/me/usage-ledger` and Settings
show this history separately from the still-enforced legacy counters. The
ledger is not yet the entitlement authority: legacy AI replies need review,
calendar-month resets differ from paid billing periods, concurrent quota
reservations are not yet enforced from ledger totals, and Stripe is not live.

### Metric-definition boundary and delivered scope

The current analysis profile is a snapshot of a specific uploaded file and its
cleaning mode. A metric definition should therefore reference that analysis
and its file, carry an owner ID, calculation type, validated source column and
version, and be calculated by the same parameterized DuckDB path as live
filters. The backend must reject identifier/free-text columns for numeric
aggregates and label distinct counts as recorded values, not verified real-world
entities. Approval creates a new immutable version; old dashboards continue to
use their saved values. Migration 005 and the owner-only API now store these
revisions, preview SUM/AVG/COUNT/DISTINCT COUNT against the saved file, and
calculate current definitions. The web dashboard has a review/approval form.
Suggestions, filter-aware approved metrics and reuse across analyses remain
future work. Approved definitions can now be pinned as saved dashboard cards;
their values are explicitly labelled as full-dataset calculations.

## First delivered increment

The existing live-query engine now accepts validated typed-date ranges and
recalculates chart/KPI results using the saved data. The web dashboard has a
date-range control and reveals each KPI's source, aggregation and active filters.
Numeric range controls now use the same query path and reject malformed,
non-finite or descending bounds. The live-query path also preserves weighted
averages and represents empty results as missing. Broader time-period comparisons
and conversational editing remain subsequent stages.

## Second delivered increment (11 October 2026)

Users can preview and approve their own metric definitions on a completed
analysis. The backend validates columns and aggregation roles against the saved
schema, executes only known aggregate functions, keeps all prior revisions,
and prevents a definition from being evaluated against a different uploaded
file after a rerun. Current definitions appear separately on the analysis page
with value, source, row count and revision. They do not silently replace saved
KPIs or spend an AI follow-up. A truncated import is clearly labelled as a
sample. The feature does not yet satisfy the wider semantic layer or billing
requirements in the master brief.

## Third delivered increment (11 October 2026)

Migration 006 stores immutable, owner-scoped dashboard layout revisions. The
API returns a default layout for existing analyses and accepts only validated
hide, show, move and undo commands against known chart IDs. Each change checks
the expected version to avoid lost updates. The web analysis page saves chart
order and visibility and can undo the last change. The original `Analysis.charts`
JSON remains intact, and layouts reconcile safely when regeneration changes
chart IDs. This is layout editing only: chart calculations, new chart creation,
conversational edits, palette choices, and dashboard-wide filter persistence
were added in the next increment.

## Fourth delivered increment (14 October 2026)

The versioned dashboard specification now stores pinned approved metric IDs,
validated saved filters, and per-chart colour palettes as well as chart order
and visibility. The web report displays pinned metric cards near its KPIs,
offers a compact metric editor, restores saved filters on load, and lets owners
choose an Aurora, Sunset, Ocean or Garden palette for each chart. Undo restores
the previous saved specification. Metric cards currently show full-dataset
values even when interactive filters are active, with that scope disclosed.

The Data Assistant recognises a small set of exact text commands for these
saved edits. Chart titles and approved metric names must match unambiguously;
ordinary data questions still use the existing chat path. Text commands do not
create new chart calculations or spend an AI follow-up. The backend validates
owner, analysis, chart IDs, metric IDs, filter columns, palette names and the
expected revision before saving.

## Revenue chart clarity (16 October 2026)

Implemented first-date alignment, a labelled first measured amount, value axes fitted to the actual amounts, and straight time-series segments. Shared chart presentation covers saved reports, live filters and export captions. Samsung verification confirmed Northwind starts at 146,555.35 on 3 February 2025; focused backend and web checks pass.

Revenue chart correction: month-year axis labels (for example Feb 2025) retain the underlying weekly observations and exact tooltip dates. The time-series scale fits the observed amounts, removing the unnecessary empty space down to zero.


## Admission audit fixes (16 October 2026)

The supported admission schema now gets deterministic context and outcome-focused chart selection, guarded by the full field combination. Recorded admission chance and undergraduate grades lead the KPIs; grade averages cannot be summed. GRE/TOEFL, application ratings, research codes and score scales have explanatory names. Four charts compare recorded chance by research/SOP/LOR and show the grade/chance relationship. Group labels include actual supplied record counts; scatter grade axes fit the observed range, with admission chance shown as percentages. Comparison defaults use averages; admission comparisons calculate percentages and percentage-point gaps while preserving raw filter group values. Unsubstantiated rule-generated owner/timing fields are omitted.

Saved adm_data analysis 8211ec3e-091d-44f8-ae9e-157d8fa6537c was refreshed from its complete 400-record analysed file using scripts/repair_admission_report.py, without an AI request or quota charge. Existing chart IDs are reused on subsequent repairs. The original file and values were not changed. The valid but uncommon CGPA 6.8 stays in file checks and saved evidence, rather than being repeated as the main insight and action. Summary explicitly distinguishes recorded chances from actual acceptance rates and avoids causal or time-trend claims. Chrome verified average recorded chance 72.44%, grade 8.60/10, correct sample sizes and percentage scatter labels. Backend checks cover the domain guard, score-total rejection, group counts, live percentage aggregation and percentage-point comparisons. Web/mobile type-check and lint pass (pre-existing web logo warning); mobile core tests pass.


## Survey import and cleaning repair (16 October 2026)

Fixed credible first-row headers being replaced by later, denser data rows. Header vocabulary now matches tokens rather than arbitrary substrings. Identifier/code fields and code-shaped values are protected from semantic merging; structured question/answer survey categories bypass semantic merging entirely. Lone colon markers are preserved as unavailable numeric values. Smart cleaning keeps unpublished survey percentages and optional notes empty and retains their records. Optional note fields no longer incur missing-data warnings or score penalties.

Structured published-percentage tables no longer receive an overall average KPI, question-mixing charts, or inferred respondent counts. Their chart uses one explicitly described question, answer and survey-group selection; it excludes supplied Average rows and refuses mixed or conflicting selections. All 52 question codes in the current dataset remain available with their question wording. Percentage comparisons require one question/answer/group and a country comparison; unscoped approved averages are blocked. Valid survey percentages within 0-100 are not treated as outliers merely for differing across unrelated questions.

Rebuilt analysis 29113565-2cd9-4863-9bf0-f21ca55982e1 from the intact original CSV using scripts/repair_survey_report.py, with no AI request. Original and previous cleaned files are retained. The repaired copy has 34,020 rows, 52 question codes, 32,171 published percentages and 1,849 unavailable percentages, with no row removal or imputation. Optional notes remain blank in 18,724 rows; 1,595 answer labels are unavailable. Removed the former Average 9 KPI and misleading generated findings/recommendations. Corrected the original upload's stored header/row-count profile.

Chrome verified the corrected record explanation, summary, question selector and live filtering. For b1_b / Very widespread / Lesbian, the first country values were Italy 65%, Bulgaria 61%, Croatia 56%, matching direct file queries. Remaining quality checks concern unavailable percentage/answer fields; optional notes and cross-question wide-spread flags are gone. Checks: 90 passed and seven database-integration tests skipped in the pipeline suite; 40 passed for final safety/quality/language/wrangling checks, plus targeted scope checks. Web/mobile type-check and lint pass (pre-existing web brand-logo warning). Browser connection reset during review; verification resumed successfully in a fresh Chrome tab.
