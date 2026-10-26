# Zephyr project status

Updated 16 October 2026. This tracks the current implementation; older review
scores and the June feature roadmap are historical planning documents.

## 16 October evidence checks

- 22 October deployment preparation: production Compose now passes the public
  website, API and Supabase values into the Next.js build, requiring each value.
  The production image build rejects localhost URLs. A one-time migration service
  runs `alembic upgrade head` after Postgres becomes healthy; API and analysis
  workers wait for it to finish successfully. Compose configuration validates
  with representative values. A staging deployment, production database URL,
  HTTPS certificate/domain, restore drill and end-to-end login/upload/export
  check still need validation before public launch.

- Release reliability gate added: eight synthetic source files, each in original
  and reversed row order, pass through the upload defaults and real analysis
  pipeline with AI disabled. All 16 runs pass. Default cleaning now preserves
  repeated records and missing amounts; semantic category merging is opt-in.
  The web uploader uses the same defaults. Numeric-looking ID/code/postal fields
  retain their leading zeros through parsing and cleaning. Existing saved
  reports are not rewritten and need a fresh upload to recover values previously
  lost during import. Details and repeatable commands:
  `backend/evals/reliability/README.md`.

- Fresh-database integration checks exposed an initial migration dependency on
  Docker's UUID extension setup. Migration 001 now creates the extension itself.
  All 19 saved-metric, ownership, usage and feedback checks pass after migration
  in a new disposable database; the application database was not migrated or
  modified. Import/survey/workbook checks: 51 passed. Pipeline/filter/comparison/
  language regressions: 109 passed, seven local DB checks skipped (covered by
  the separate disposable-DB run). Website type check and new Python lint pass.
  This gate does not certify AI prose, hosting, backups or release devices;
  public production readiness remains unconfirmed.

- Samsung verification of descriptive names is complete. The device initially
  retained the old mobile bundle; the verified Zephyr Expo server on port 8081
  was restarted with `--clear`, and the app was reloaded. Confirmed the "What
  this data is about" section, "Weekly sales records by revenue range" title,
  and supporting-record heading "17 Nov 2025 · North America · Apparel · Online",
  with position 493 displayed separately. The record still shows average order
  value 89.45 and the matching date/region/category/channel. No new AI request,
  share, export or analysis rerun was needed. Screenshots:
  `mobile/artifacts/samsung-data-about-2026-10-16.png`,
  `mobile/artifacts/samsung-weekly-record-chart-title-2026-10-16.png`, and
  `mobile/artifacts/samsung-descriptive-sales-record-2026-10-16.png`.

- Descriptive record names are implemented. Northwind supporting records now
  lead with week, region, category and channel; analysed-file positions remain
  secondary references. Actual saved position 493 reads "17 Nov 2025 · North
  America · Apparel · Online". Existing name/ID fields identify other records;
  missing names are not invented. A conservative saved-schema check enables
  weekly-sales terminology only when the required date/dimensions/measures exist.
  The report now explains what its weekly sales records contain, and its chart
  is titled "Weekly sales records by revenue range". Owner/shared charts, live
  filters and exports preserve this context and the original values.
  Tests: 64 focused backend checks and 55 Docker database/feedback/export checks
  passed. Ruff, website/mobile types and lint pass (existing website image
  warning remains); all 11 mobile core tests pass. Actual Northwind labels/title
  were read back without an AI call or analysis rerun; no active analyses were
  present before reload. Samsung disconnected during this increment, so device
  review of the new names is pending.

- Revenue range charts now use horizontal bars with full readable ranges,
  visible entry counts and a measured most-common-range explanation. Existing
  saved charts are presented this way without changing their counts or requiring
  an analysis rerun. New range labels retain two decimals rather than rounding
  whole bands to K/M abbreviations. Rounded limits and the 10,000-entry chart cap
  are disclosed; count axes are not formatted as money. Website/mobile, live
  filter patches and PDF/Excel exports use the same range/count presentation.
  Empty histogram filters now clear stale bars. Samsung confirmed all 12 saved
  revenue ranges and their counts, including the most common approximate
  12,000-to-14,000 range with 261 of 936 entries. Screenshot:
  `mobile/artifacts/samsung-revenue-ranges-clear-2026-10-16.png`.
  Final chart/filter/export suite: 56 passed; Docker suite including database
  ownership checks: 65 passed. Ruff, website/mobile types and lint pass; all 11
  mobile core tests pass. Website retains its existing brand-logo image warning.
  Backend/worker reloaded and API healthy. The local website is using its
  development runtime; device visual review was performed on Samsung.

- Ambiguous "How many fall into each..." chart captions now explicitly count
  entries. New charts explain that one entry is one line of data in the report;
  saved chart captions are corrected on read for website/mobile/shared reports
  and exports, with all plotted values unchanged. Samsung confirmed "Number of
  entries in each region" and "Number of entries in each revenue range" on the
  existing Northwind report. Chart/presentation/export/API checks: 44 passed;
  Ruff passes. Backend and worker reloaded; API health is healthy. Screenshots:
  `mobile/artifacts/samsung-region-count-caption-2026-10-16.png` and
  `mobile/artifacts/samsung-chart-count-caption-2026-10-16.png`.

- Samsung follow-up review is complete after reconnecting the device. Verified
  the new ranking headline and gap in the saved chat reply, forecast baseline/
  range/planning guidance, and the specific average-order-value action. The chat
  link opened 312 North America entries; the action link opened exactly entry
  493 with average order value 89.45 and matching context. Entry details expand
  correctly, and text/buttons were readable without clipping in the reviewed
  views. No new AI question, export, share or analysis rerun was needed.
  Screenshots: `mobile/artifacts/samsung-answer-headline-2026-10-16.png`,
  `mobile/artifacts/samsung-forecast-planning-2026-10-16.png`,
  `mobile/artifacts/samsung-specific-action-2026-10-16.png`, and
  `mobile/artifacts/samsung-chat-entry-link-2026-10-16.png`.

- Business wording now leads with the measured result: grouped answers name
  the highest/lowest group and its absolute gap to the next group. Ties are
  checked across all groups, including those hidden by the display limit;
  numbered groups include their field name (for example, Store 20). Saved
  audited comparisons receive the same wording on read without changing history
  or making another AI call.
- Recommendation titles now identify the measured field/value or the specific
  blank/repeated information to check. Actions explain how to verify it against
  the source and when to keep valid differences. Context comes from saved
  measurements, with supporting-entry links preserved. Website, mobile, shared
  reports and exports use the same presentation functions (`plain_business_v3`).
- Forecasts now include the latest figure, the possible range, and guidance to
  check plans at both ends of that range. They distinguish monthly totals from
  individual weekly entries, explain short history/wide ranges when applicable,
  and avoid a directional claim when the range overlaps the latest month.
- Read-only offline checks used all three supplied files: Walmart sales,
  EI sales workbook and sponsor register. Original files were unchanged; source
  row counts differ from earlier cleaned reports. The host QA adapter bypassed
  its missing Arrow conversion dependency while retaining the production parser
  and deterministic analytics. No paid AI request or analysis rerun occurred.
  Full backend suite: 479 passed, 17 skipped; final focused suite: 66 passed.
  Docker database/feedback/export regressions: 83 passed. Ruff and mobile
  TypeScript/lint pass. The running backend/worker were reloaded, and the saved
  Northwind report/reply were read back with the new wording. Samsung was no
  longer connected for this increment; new device wording review remains pending.

- All three investigation features are implemented on the website and mobile:
  affected-entry views, verified group comparisons, and recommendation figures
  with supporting-entry links. Owner-only endpoints calculate from the analysed
  file without an AI call or allowance charge. Chat can request a validated typed
  comparison plan; replies use actual calculated figures, with audit method
  `measured_chat_queries_v1`. Field roles, filters, rates, weights and missing
  values are checked before execution. Model-written numbers are ignored.
- Links bind to saved report revisions and criteria; affected counts must match.
  Entries are paginated (25 website, 10 mobile), with up to 20 fields and readable
  dates/amounts. Comparisons show up to 50 groups. Positions refer to the analysed
  copy; sampling and cleaning limitations remain visible. Original blanks filled
  during cleaning receive source-count explanations rather than invented links.
- Samsung confirmed North America leads revenue at 4,646,243.21, with 312
  matching entries, and opened the 13 revenue entries outside the saved limits.
  Backend verification: full host suite 469 passed, 17 skipped; final focused
  suite 22 passed; database-backed Docker suite 41 passed. Changed Python lint,
  website/mobile types and lint, and all 11 mobile core tests pass. The website
  retains its existing brand-logo image warning. API and worker were restarted
  after testing. iOS device QA remains pending.
- Final live Samsung chat test answered "Which region brings in the most
  revenue?" with verified totals and entry links; audit confirms
  `measured_chat_queries_v1` succeeded. The initial live attempt declined the
  question; clarified planner instructions fixed that exact retest. The declined
  answer did not consume an app allowance; the successful answer did. Final
  chat/investigation/AI regression suite: 106 passed, with Ruff passing.
  Recommendation figures showed average order value 89.45 and opened exactly
  entry 493, matching its date, region, category and channel. Screenshots:
  `mobile/artifacts/samsung-chat-comparison-2026-10-16.png`,
  `mobile/artifacts/samsung-recommendation-figures-2026-10-16.png`,
  `mobile/artifacts/samsung-recommendation-entry-2026-10-16.png`.

- Follow-up file-check review corrected wording that was simple but too vague.
  Unusual-value notes now name the measure and its actual comparison limits,
  using separate lower/higher counts when saved. New checks retain both counts;
  legacy reports keep their measured total and bounds without inventing a split.
  The report explains that review limits come from the file rather than business
  targets, and asks users to check expected differences before correcting entries.
  Confirmed on the Samsung: revenue flags 13 entries below about 5,415.3 or above
  about 20,504.43; marketing spend flags 18 above about 2,620.53. Both are saved
  measurements, not a new AI interpretation. Focused wording/check suite: 20
  passed; Ruff passes. Screenshot:
  `mobile/artifacts/samsung-specific-file-checks-2026-10-16.png`.

- The language review now covers the whole report, not only chat. A deterministic
  presentation layer rewrites saved insight, forecast and recommendation wording
  on read without changing measurements, feedback, audit evidence or stored history.
  Forecasts use approximate planning language and retain their uncertainty;
  single-entry extremes remain tied to their own entry. File checks explain blanks,
  repeats and unusual numbers, which may be valid. The numeric check score and
  its explanation are optional details. Existing audited summaries also receive
  plain wording with matching calculation disclosures. Shared reports and exports
  use the same presentation functions; no AI request or analysis rerun is needed.
- Web/mobile labels now read "What stands out", "What to do next", "What we found",
  "Why this helps", "Looking ahead" and "What to check in your file". Confidence
  proxy bars were removed from default insight cards. Forecast uncertainty is
  fully visible. Samsung review confirmed forecasts, the unusual-entry card,
  recommended action, file checks and the optional score disclosure. Screenshots:
  `mobile/artifacts/samsung-actions-plain-2026-10-16.png`,
  `mobile/artifacts/samsung-outlook-plain-2026-10-16.png`,
  `mobile/artifacts/samsung-file-check-details-2026-10-16.png`.
  Twelve focused presentation tests cover meaning, numbers, uncertainty,
  idempotence and preserving the original data. Docker report/feedback/export/
  ownership regressions: 33 passed. All 11 mobile core tests pass; website and
  mobile types/lint pass (the existing website brand-logo image warning remains).
  Final backend suite: 445 passed, 16 skipped. The file-check disclosure was
  opened and closed successfully on the Samsung. The final API was reloaded;
  no new AI question, share action or analysis rerun was needed.

- Samsung chat review exposed technical formulas and duplicate versions of the
  same answer. Chat now renders concise business wording, deduplicates equivalent
  facts, and keeps routine file counts/formulas out of the reply. Calculation
  provenance remains internal; material cleaning/sampling notes remain visible
  in plain language. API presentation also reformats older audited replies without
  rewriting stored history or making an AI request. Confirmed on the Samsung:
  "Total revenue is 12,285,143.73." Screenshot:
  `mobile/artifacts/samsung-chat-plain-language-2026-10-16.png`.
  Product wording rules are in [PRODUCT_LANGUAGE.md](PRODUCT_LANGUAGE.md).
  Final suite: 433 passed, 16 skipped; 23 Docker chat/database tests passed;
  changed Python files pass Ruff. Both local services were reloaded.
- New and rerun analyses now use a server-computed recommendation catalogue.
  AI may rank existing action IDs; free-form recommendations are excluded,
  including claims that reuse a real number for another field or business meaning.
  Selection and rejected IDs are saved in metadata and the downloadable profile.
  Forecast actions independently check whether the interval includes the latest
  observation; serial numbering does not create an entity-coverage action.
- Chat selects saved fact IDs and renders canonical measured statements with
  source calculations. Totals, arithmetic averages, ranges, category counts with
  denominators, and distinct recorded values remain attached to their own fields.
  Sampling, cleaning and material source-gap disclosures survive selection. Old
  summary/insight prose and upload instructions are not evidence. Invalid and
  unsupported answers do not consume the user's allowance; database-backed
  endpoint tests verify this.
- At the earlier saved-fact checkpoint, chat was limited to saved measurements.
  The typed calculation planner described above now adds filtered/grouped
  comparisons. Causal explanations and unsupported predictions still return a
  limitation. Model selection determines relevance; this does not verify the
  source file's real-world accuracy. Existing recommendation cards require a
  full analysis refresh to use the catalogue; existing reports use the chat
  checks immediately.
- Read-only Docker QA on Northwind found 46 facts and confirmed revenue of
  12,285,143.73 across 936 records. No live AI request was made and no account
  allowance changed. All 38 Docker evidence/database tests passed, including
  ownership and failed/unsupported-answer accounting. The API and worker were
  restarted after confirming no active jobs. Samsung remains connected; this
  increment changes backend behavior only. Final host suite: 430 passed,
  16 skipped; Ruff passes for all changed Python files. A new phone chat attempt
  and iOS device QA had not been performed at this checkpoint. The later chat
  presentation review above verified the existing reply without submitting a
  new AI question; iOS device QA remains outstanding.

## 15 October live QA

- Executive summaries now render canonical statements from measured facts.
  The model may rank known fact IDs; it cannot rewrite their values, subject,
  aggregation, denominator or scope. Unknown IDs fall back to deterministic
  selection. Sampling, source gaps and material cleaning qualifications survive
  selection. Numeric facts are checked against their own field and aggregation;
  identifiers and serial numbering do not become performance measures. Cosmetic
  display labels cannot rename a measure's business meaning.
- Summary statements carry source, calculation, values and scope in
  `analysis_evidence.summary_checks`. Web summaries expose "How calculated";
  the Samsung exposes "How the summary was calculated". An owner-only
  `POST /analyses/{id}/summary/refresh` updates older summaries from saved
  measurements, preserves the prior text, and makes no AI request or quota
  reservation. It does not regenerate charts or repair incorrect source data.
  The Profile JSON download uses the current saved profile so refreshed
  evidence is included. Profiles now retain weighted-average provenance.
- Live Samsung summary update passed for the 936-record Northwind report.
  Its summary shows North America at 312 records (33.3%) and Online at 533
  (56.9%); the calculation disclosure opened. Read-only source regressions
  covered Northwind, Walmart and the EI workbook. Backend suite: 417 passed,
  15 skipped. Website/mobile types and lint pass, with the existing website
  brand-logo image warning. At this checkpoint only executive summaries had
  this constraint; the recommendation/chat increment is documented above.
- PDF and Excel exports now carry saved dashboard charts. The Samsung PDF
  initially stayed at two pages because the running Docker API had not picked
  up file changes. After restarting the backend, an actual phone download was
  verified as five pages with seven charts and the first chart on page one.
  Mobile exports use unique cache filenames and remain available to receiving
  viewers; no third-party destination is needed to verify the downloaded file.
- Latest Samsung Excel export was pulled from Zephyr's private cache and
  inspected: seven native chart objects, Charts and Chart Data sheets, and the
  updated summary. The Ask Zephyr retest exposed that the installed build did
  not resize its root view for the keyboard. Chat now enables Android height
  avoidance with the navigation header offset (using Expo Router's supported
  hook). Typing and Send remain visible above the keyboard, and dismissal
  restores the composer. No test chat message was submitted. Mobile types,
  lint and all 11 core tests pass after the fix. iOS device QA is still pending.

- Docker backend, worker, PostgreSQL and Redis started locally. All seven
  dashboard/metric API tests passed against PostgreSQL, including saved layout,
  palette, pinned metric, validated filters, ownership and undo.
- The signed-in web report loaded in Chrome in dark and light themes. The
  summary, KPI and charts are readable. Changing a chart palette persisted as
  layout version 1, and undo restored Aurora in version 2. Data-quality detail
  text received a dark-theme contrast fix; the rounded source check score is
  labelled as a check score rather than literal completeness.
- The Samsung SM-A025G was connected via ADB and the development build loaded
  from Metro. Metro's Expo-account manifest request failed in this restricted
  environment, so local testing used `EXPO_OFFLINE=1`. The local mobile API URL
  had still pointed at the Android emulator (`10.0.2.2`); the untracked local
  `.env` now uses `127.0.0.1` for USB reverse routing. A phone-side request to
  the analyses API returns 401 without a token, confirming it reaches the host.
  USB reverse routes must be restored after reconnecting the phone.
- Samsung Google sign-in ended in a Chrome Custom Tab at `localhost:3000` with
  `ERR_CONNECTION_REFUSED`. The app requests `zephyr://auth/callback` and its
  installed Android build declares the `zephyr` scheme. The user supplied the
  accessible Zephyre project `kegwxfleotwojusdowfb`. Its redirect allow list
  was empty; `zephyr://auth/callback`, the mobile recovery variant,
  `http://localhost:3000/auth/callback`, and the local web callback's
  `redirectTo=**` query variant were added and verified in Supabase.
  Ignored local web, mobile and backend environments now use that project's
  URL and public anon key. Old-project service-role and JWT secrets were
  cleared from the local backend environment; it was recreated and its health
  endpoint returned 200. The new project's active JWT key is ECC (P-256), so
  token verification can use JWKS. The Google Cloud OAuth client now has the
  project's Supabase callback URI, and Supabase shows the Google provider as
  enabled. Web sign-in reached Google's account chooser and the Supabase code
  exchange completed after the local Next.js server was restarted with network
  access. Chrome then blocked the `/dashboard` page with `ERR_BLOCKED_BY_CLIENT`,
  so a visible signed-in dashboard remains unverified. On Samsung, Expo's
  Custom Tab proxy initially closed before Google appeared. Opening the auth
  session without a separate task reached Chrome, but Supabase redirected to
  `localhost:3000` and Chrome reported `ERR_CONNECTION_REFUSED`. The native
  auth redirect is now the exact allow-listed `zephyr://auth/callback`, including
  confirmation and recovery flows. After reopening the development build and
  loading a fresh Metro bundle, device logs confirmed that Supabase received
  `zephyr://auth/callback`, and the Samsung reached Google's account chooser.
  Google returned to Zephyr, but the callback screen initially waited only on
  `Linking.useURL()` and remained on “Confirming your account.” It now also
  reads Expo Router's callback parameters and exchanges the code once. The
  Samsung reached the signed-in workspace and displayed five analyses.
  The five visible analyses need an ownership check before any migration of
  records from the previous Auth project. The privileged
  service-role key was not stored: automatic approval review first rejected
  revealing it, then rejected copying it through the system clipboard because
  other applications could read the clipboard. Account deletion remains
  unavailable until the user places the new key in the ignored root `.env`.
  Web and mobile type/lint checks pass (web still has the existing brand-logo
  image lint warning).
- Production configuration no longer requires the legacy HS256 JWT secret for
  ECC-signed Supabase projects. JWT verification still rejects HS256 tokens
  without that secret; all six focused JWT tests passed.

## Implemented in this working tree

- Owner-scoped metric definitions: a user can preview SUM, AVG, record count or
  distinct recorded-value count on a completed analysis, approve it, and revise
  it without overwriting earlier versions or generated KPI cards. Migration 005
  stores the versions against the analysis and its source file. Calculations
  validate source columns and disclose row counts and sampled imports. This is
  the first semantic-definition workflow; approved definitions can now be
  pinned as saved cards. See [the implementation plan](IMPLEMENTATION_PLAN.md).

- Saved dashboard editor: owners can hide, show and reorder charts, choose a
  colour palette per chart, pin approved metrics, save validated filters and
  undo changes. Migration 006 keeps immutable revisions; the API checks chart
  and metric IDs, ownership and expected version. Exact text commands in the
  Data Assistant use the same saved edits. Generated chart calculations are
  unchanged; model-driven chart creation remains pending.

- AI chat allowance: provider failures now return a saved failure status and
  do not consume the current AI follow-up counter. Successful responses save
  the configured model and prompt/completion token counts with the message.
  A billing-period usage ledger and cost estimates are still pending.

- Operational usage ledger: migration 007 backfills analysis and assistant
  message events without guessing whether ambiguous older AI replies succeeded.
  New analyses reserve an event and the worker marks completion or failure;
  new chat replies record outcome, model and tokens. Settings displays these
  observed counts alongside the existing enforced counters. Subscription-period
  entitlements, atomic ledger-based reservations and billing are still pending.

- Date-range filters now use typed date columns from the saved profile and
  recompute charts and KPI values with parameterized DuckDB queries. Invalid or
  reversed dates are rejected. Numeric range filters have a measure picker and
  reject malformed or reversed bounds. KPI cards show source, calculation and applied
  filters. A filter with no matching rows shows no KPI value instead of the
  original unfiltered number. Weighted KPIs retain their weighting under live
  filters. This does not consume an AI request. See the phased architecture in
  [the implementation plan](IMPLEMENTATION_PLAN.md).

- Walmart accuracy fixes: infer date order from unambiguous values in the same
  column; classify store numbers and holiday flags as grouping fields; average
  prices and holiday-week sales per record; flag forecasts whose uncertainty
  range includes the latest observed month so directional action cards are not
  generated. The supplied 6,435-row source verifies 5 Feb 2010–26 Oct 2012,
  average fuel price 3.36 and 45 stores. The saved Walmart report was
  regenerated after user approval and verified on the Samsung. Its summary no
  longer implies an unsupported currency, and its forecast states when the
  change direction is uncertain.

- 8 October native smoke: Android development build completed and was installed
  on the USB-connected Samsung SM-A025G (Galaxy A02s), Android 12, ARMv7.
  Metro loaded the current source and the native sign-in screen rendered without
  a startup error. USB forwards ports 8000/8081; Metro must accept IPv4 (use
  `--lan`, since `--localhost` bound only to IPv6 here). Mobile type/lint and all
  11 core tests passed. After user sign-in, native checks passed for the live
  analysis list, corrected EI workbook dashboard (437 entries, 120-day average
  SLA, six-region chart), chart rendering/hide control, account/usage settings,
  Android document picker and session persistence after force-stop/relaunch.
  No startup/runtime error was observed in these checks. Native analysis creation,
  AI chat requests and PDF/Excel export completion remain untested; no analysis
  quota was consumed. Screenshots are in `mobile/artifacts/samsung-*.png`.

- Operational workbook regression fixes: exclude unrelated worksheets from the
  main table and disclose them in parser metadata; restore typed dates after
  header promotion. Treat serial-number columns as identifiers, remove their
  performance correlations, average durations, and avoid empty or constant
  metrics in charts. Files without varying measures get record-count charts.
  Geographic groups merge case, spacing and hyphen variants consistently across
  summaries, charts and filters, while preserving source values. Average series
  use grouped bars and missing chart values stay missing. Quality checks rank
  material findings first, disclose empty fields separately and explain scoring.
  Repeated coverage/identity recommendations for the same field are merged.
  Verified against the supplied EI workbook without modifying it: 437 main-table
  records (previously 441 including notes), six geographic groups, typed service
  order/RFI dates, 120-day average SLA, no serial-number performance charts,
  and an explained analysis-check score of 84/100 with 12 empty fields disclosed.
  Backend regression suite: 384 passed. Website/mobile type and lint checks pass
  (website retains its existing brand-logo image lint warning).
  Mobile browser smoke passed with the new empty-field/scoring explanations;
  fixture traffic covered charts, upload, feedback, exports, chat and settings.
  The Celery worker was restarted with the updated engine.

- General analysis evidence improvements: preserve source completeness before
  cleaning, reconcile all recorded row removals, and disclose placeholders and
  estimates. Compute distinct recorded identity/name values separately from row
  counts, excluding blank and `Unknown` labels. These are not verified identities.
  The canonical profile, saved metadata, AI narrative/chat context, website and
  mobile dashboard now carry the evidence and limitations.
- Recommendations include targeted coverage/counting checks. AI candidates
  without quantified evidence or with figures absent from the measured profile
  are rejected (display rounding and simple category percentages are supported).
  Categorical-only diversification filler is filtered. Numeric matching does not
  prove semantic correctness or causation; this remains a conservative guardrail.
  Unsupported monetary benefit estimates are hidden, including the deterministic
  rules' former arbitrary 1%/3% calculations.
- These changes apply to new or regenerated analyses. Existing saved dashboards
  retain their original results until rerun. No paid AI regeneration was triggered
  during this verification.

- Android/iOS mobile app in `mobile/`, using Expo SDK 57 and the existing API.
  Includes email authentication/recovery, single-file uploads, analysis lists,
  dashboards/charts, feedback, AI chat, export/sharing and account settings.
  See [mobile setup](../mobile/README.md) for local development configuration.

- Account deletion: authenticated `DELETE /api/v1/users/me` removes the Supabase
  identity, local account and database-owned records, and the account's upload
  directory, including cleaned files and profiles. The settings button confirms
  deletion, clears browser state, and returns to login. Running analyses and paid
  subscriptions that have not been canceled block deletion. Configure the
  server-side `SUPABASE_SERVICE_ROLE_KEY` to enable it.
- New local accounts must pass a live Supabase user check. This prevents a
  deleted account's unexpired token from auto-provisioning another local account.
- Successful analyses record UTC `completed_at`; reruns clear it until completion.
  Historical rows remain NULL rather than receiving invented completion times.
- Successful PDF and Excel generation records `export_events`. This measures
  generated exports, not whether the browser finished downloading them.
- Migration `004_completion_exports` adds the completion column and event table.
  Apply it with `cd backend` and `alembic upgrade head` before running this version.

Deletion spans Supabase, PostgreSQL, and local files, so it cannot be one atomic
transaction. A remote or file cleanup failure returns an error; the local
database transaction rolls back and the owner can retry. A remote account
already removed on a prior attempt is treated as successfully deleted on retry.
Partial file cleanup and local commit failures can require a retry. No real
accounts were deleted while implementing this feature.

Supabase documents that existing JWTs can survive account removal until expiry:
[user management](https://supabase.com/docs/guides/auth/managing-user-data).
The live check above closes local auto-provisioning through such a token.

## Dashboard editor verification (14 October 2026)

- The production web build, TypeScript check, ESLint and focused text-command
  tests pass. ESLint retains the existing `brand-logo.tsx` image warning.
- Seven targeted dashboard/metric API tests passed against local PostgreSQL on
  12 October. After adding chart palettes, two pure calculation/layout tests
  passed and Ruff passed; the new palette API test still needs a running local
  PostgreSQL service.
- The dark web shell was inspected in Chrome. The analysis report could not be
  inspected because the backend was offline. ADB reported no connected Android
  device, so Samsung QA remains pending.

## Samsung mobile verification (15 October 2026)

- On a connected SM-A025G using the local backend, Google OAuth returned to the
  Zephyr app and opened the signed-in workspace. Sign-out and Google sign-in
  succeeded again after the login keyboard check.
- Uploaded the 68 KB fictional Northwind CSV from the Android file picker. Its
  936-row analysis progressed to Completed. A suggested chat question returned
  an answer. Both PDF and Excel exports opened Android's share sheet with the
  corresponding file type. Sharing to a third-party destination was not tested.
- The login form now hides its introductory panel while the keyboard is open.
  Email, password, and Sign in stayed visible when each field was focused on
  the Samsung. Chat answers render bold Markdown labels without literal `**`.
  Mobile Expo lint, TypeScript, and all 11 focused tests pass.
- Ask Zephyr's question composer now rises above the Samsung keyboard. The
  question text and Send button remained visible while typing, and the composer
  returned to the bottom when the keyboard closed. Expo lint, TypeScript, and
  the 11 mobile tests passed again after this fix.
- The dashboard's generated summary still needs evidence review: this sample
  described regional/category representation as equal without a visible count
  breakdown. The device test proves the journey works, not factual accuracy of
  every generated conclusion.

## Verification for the earlier batch

- Analysis improvements: all 378 backend tests passed against the running test
  environment, including new multi-domain evidence and cleaning regression tests.
  Ruff, website/mobile types and lint passed (website retains its existing
  `brand-logo.tsx` image warning). Mobile fixture smoke checks also verified the
  new source-completeness and counting disclosures.
- Full supplied sponsor-register CSV reproduced offline: 143,161 source records
  become 142,632 after 529 normalized exact duplicates are removed, with zero
  unexplained change. The original 447 byte-for-byte duplicate count differs
  because cleaning normalizes text. Cleaned organisation names have 127,640
  distinct recorded values. Source completeness scores 81/100; cleaned checks
  score 100/100. Neither score verifies real-world factual accuracy.

- Mobile: type checking, lint, 11 focused tests and Expo Doctor passed.
  Android/iOS/web JavaScript exports succeeded. Browser smoke tests passed using
  intercepted fixture traffic, including chart rendering, uploads and exports.
  EAS native development builds submitted: [Android APK](https://expo.dev/accounts/visaatlasdigital/projects/zephyr-mobile/builds/307afddf-73c0-4f12-abc0-16f76d7b9303)
  and [iOS simulator](https://expo.dev/accounts/visaatlasdigital/projects/zephyr-mobile/builds/3b8f5315-637a-485b-a3b2-9a8ed3e6ca82).
  Native compiler results, device testing and live backend/email callback testing
  are pending. No store submission was made.

- Backend: 359 tests passed; 10 PostgreSQL integration tests skipped because
  no test database was reachable, including the new account cascade test.
- Frontend: `npm run type-check` passed.
- Ruff passed for all changed Python files.
- Alembic upgrade and downgrade SQL generated and validated offline; no live
  database was migrated. `git diff --check` passed.

## Already completed in earlier commits

- Shared KPI/chart aggregation, currency recognition, and weighted percentages.
- Scatter chart behavior, chart labels, token budgeting, and business wording.
- Rule-based recommendation calibration and owner feedback.
- AI service regression coverage and clean-clone test configuration.

## Remaining

- Mobile: finish cloud build verification and iOS device testing, then configure
  owned application IDs and HTTPS environments for release. iPhone device
  builds require Apple signing and registered devices.

1. Run and validate the paid AI confidence benchmark; AI confidence tiers are
   still unmeasured. The committed results are from the offline benchmark.
2. Set canonical plan prices and currency. The ORM uses `starter` and
   `professional`; the product document describes `Pro` and `Business` prices.
   Resolve that mapping before computing MRR or ARPU.
3. Define and implement billing/trial lifecycle tracking and NPS collection.
   Tables alone cannot measure events the application does not generate.
4. Build the product operations dashboard against those agreed metrics.
5. Run database integration tests and apply the migration in a test deployment.
6. Capture real dashboard screenshots and a recorded demo, and publish the
   architecture/ER diagrams as portfolio artifacts.
7. Refresh historical portfolio scores and other source-line references after
   implementation and deployment validation.

## Revenue chart starting point (16 October 2026)

Time charts align the first measured point with its date and show a visible starting-amount marker and caption. Time-series value axes fit the measured range rather than forcing zero; negative values remain visible. Straight line segments avoid smoothing overshoots. Saved reports, filtered charts and export descriptions use the same presentation without adding observations. Northwind starts on 3 February 2025 at 146,555.35. Verified on Samsung; 63 focused backend tests, Ruff and web type-check passed. Web lint passed with the existing brand-logo image warning.

Revenue chart correction: month-year axis labels (for example Feb 2025) retain the underlying weekly observations and exact tooltip dates. The time-series scale fits the observed amounts, removing the unnecessary empty space down to zero.

Samsung correction verified: revenue now spans roughly 130k to 210k with Feb 2025 through Jul 2026 labels. Screenshot: mobile/artifacts/samsung-revenue-fitted-scale-month-year-2026-10-16.png. Twelve backend checks and eleven mobile core tests passed; mobile/web type-check and lint passed (existing web brand-logo warning).

Removed the on-chart Start label and special first-point marker at user request. Fitted revenue scale and month-year labels remain; three focused presentation tests and Ruff pass.

Pie/donut labels now show category, exact value and percentage on mobile and web. Verified on Samsung Region breakdown: Europe, APAC and North America each show 312 (33.3%). Screenshot: mobile/artifacts/samsung-pie-labels-2026-10-16.png. Mobile/web type-check and lint pass (existing web image warning); all 11 mobile core tests pass.
Report relevance filtering now omits automatic range histograms, equal record-count pies in reports with measured charts, weak relationship charts, exact duplicates, low-importance narrative findings and generic track-regularly recommendations. Applied to owner/shared responses and PDF/Excel reports; chart selection applies the same rules to new analyses. Saved evidence is preserved. Twenty-five focused checks passed across selection, relevance, API contracts, histogram rendering and exports; Ruff passes.


## Chrome admission report audit (16 October 2026)

Read-only audit of analysis 8211ec3e-091d-44f8-ae9e-157d8fa6537c (adm_data), including Chrome charts, supporting-record dialog and direct DuckDB recalculation. The cleaned file has 400 rows, nine fields, no nulls, no full-row duplicates and 400 distinct serial numbers. GRE mean 316.8075, TOEFL mean 107.41 and university-rating mean 3.0875 match the UI. Research counts 219/181, SOP/LOR summary counts and displayed grouped means agree with the data. CGPA/chance-of-admit correlation is 0.8732890993553004. CGPA 6.8 links correctly to serial 59; the source Kaggle explorer also contains this value.

Outstanding findings: (1) primary outcome chance_of_admit and CGPA are missing from the KPI/summary focus (means 0.72435 and 8.598925); (2) undefined SOP/LOR/CGPA acronyms, bare research 0/1 and generic entries obscure admission context; source data card defines SOP/LOR as ratings out of five, GPA out of ten, GRE out of 340 and TOEFL out of 120; (3) most charts compare GRE with other scores rather than the admission-chance measure; (4) chance chart uses 0-1 instead of percentages and CGPA zero baseline compresses observed 6.8-9.92 range; (5) isolated low-score warning is repeated as the main insight, recommendation and quality issue, with unsupported Operations owner and three-day timing; (6) comparison validation allows SUM(cgpa), a meaningless total for a grade average; (7) group charts omit sample sizes, including LOR=1 with just one record; (8) summary's SOP 4.0 frequency ignores tied SOP 3.5 count of 70, limiting usefulness. No actual admission-outcome field or time field exists: average recorded chance is not an observed acceptance rate, and this file cannot establish trends or causation. This audit did not change report data or implementation.

Source checked in the existing Chrome tab: https://www.kaggle.com/datasets/akshaydattatraykhare/data-for-admission-in-the-university


## Admission audit fixes (16 October 2026)

The supported admission schema now gets deterministic context and outcome-focused chart selection, guarded by the full field combination. Recorded admission chance and undergraduate grades lead the KPIs; grade averages cannot be summed. GRE/TOEFL, application ratings, research codes and score scales have explanatory names. Four charts compare recorded chance by research/SOP/LOR and show the grade/chance relationship. Group labels include actual supplied record counts; scatter grade axes fit the observed range, with admission chance shown as percentages. Comparison defaults use averages; admission comparisons calculate percentages and percentage-point gaps while preserving raw filter group values. Unsubstantiated rule-generated owner/timing fields are omitted.

Saved adm_data analysis 8211ec3e-091d-44f8-ae9e-157d8fa6537c was refreshed from its complete 400-record analysed file using scripts/repair_admission_report.py, without an AI request or quota charge. Existing chart IDs are reused on subsequent repairs. The original file and values were not changed. The valid but uncommon CGPA 6.8 stays in file checks and saved evidence, rather than being repeated as the main insight and action. Summary explicitly distinguishes recorded chances from actual acceptance rates and avoids causal or time-trend claims. Chrome verified average recorded chance 72.44%, grade 8.60/10, correct sample sizes and percentage scatter labels. Backend checks cover the domain guard, score-total rejection, group counts, live percentage aggregation and percentage-point comparisons. Web/mobile type-check and lint pass (pre-existing web logo warning); mobile core tests pass.

Final Chrome verification: the comparison tool returned recorded admission chance of 79.60% for research experience (219 records) and 63.77% without (181 records), a 15.83 percentage-point gap. Saved browser proof: mobile/artifacts/chrome-admission-report-fixed-2026-10-16.png and mobile/artifacts/chrome-admission-comparison-fixed-2026-10-16.png. The corrected report remains open.


## Survey import and cleaning repair (16 October 2026)

Fixed credible first-row headers being replaced by later, denser data rows. Header vocabulary now matches tokens rather than arbitrary substrings. Identifier/code fields and code-shaped values are protected from semantic merging; structured question/answer survey categories bypass semantic merging entirely. Lone colon markers are preserved as unavailable numeric values. Smart cleaning keeps unpublished survey percentages and optional notes empty and retains their records. Optional note fields no longer incur missing-data warnings or score penalties.

Structured published-percentage tables no longer receive an overall average KPI, question-mixing charts, or inferred respondent counts. Their chart uses one explicitly described question, answer and survey-group selection; it excludes supplied Average rows and refuses mixed or conflicting selections. All 52 question codes in the current dataset remain available with their question wording. Percentage comparisons require one question/answer/group and a country comparison; unscoped approved averages are blocked. Valid survey percentages within 0-100 are not treated as outliers merely for differing across unrelated questions.

Rebuilt analysis 29113565-2cd9-4863-9bf0-f21ca55982e1 from the intact original CSV using scripts/repair_survey_report.py, with no AI request. Original and previous cleaned files are retained. The repaired copy has 34,020 rows, 52 question codes, 32,171 published percentages and 1,849 unavailable percentages, with no row removal or imputation. Optional notes remain blank in 18,724 rows; 1,595 answer labels are unavailable. Removed the former Average 9 KPI and misleading generated findings/recommendations. Corrected the original upload's stored header/row-count profile.

Chrome verified the corrected record explanation, summary, question selector and live filtering. For b1_b / Very widespread / Lesbian, the first country values were Italy 65%, Bulgaria 61%, Croatia 56%, matching direct file queries. Remaining quality checks concern unavailable percentage/answer fields; optional notes and cross-question wide-spread flags are gone. Checks: 90 passed and seven database-integration tests skipped in the pipeline suite; 40 passed for final safety/quality/language/wrangling checks, plus targeted scope checks. Web/mobile type-check and lint pass (pre-existing web brand-logo warning). Browser connection reset during review; verification resumed successfully in a fresh Chrome tab.
