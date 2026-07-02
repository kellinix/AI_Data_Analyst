# 08 — Glossary

> **Document:** AI Dashboard Generator — Glossary of Terms  
> **Version:** 1.0  
> **Last Updated:** 2026-06-25  
> **Status:** Approved  
> **Owner:** Technical Writing  
> **Related Documents:** All documents in this `/docs` folder

---

## Table of Contents

1. [How to Use This Glossary](#1-how-to-use-this-glossary)
2. [Business & Analytics Terms](#2-business--analytics-terms)
3. [AI & Machine Learning Terms](#3-ai--machine-learning-terms)
4. [Product-Specific Terms](#4-product-specific-terms)
5. [Data Engineering Terms](#5-data-engineering-terms)
6. [UX & Product Terms](#6-ux--product-terms)
7. [Security & Compliance Terms](#7-security--compliance-terms)
8. [Infrastructure & Engineering Terms](#8-infrastructure--engineering-terms)

---

## 1. How to Use This Glossary

This glossary defines every important term used across the AI Dashboard Generator documentation. Terms are grouped thematically.

**Rules:**
1. When a new term is introduced in any document, it must be defined here first.
2. When a term from this glossary is used in another document for the first time, it should be capitalised and/or italicised to signal it has a specific definition.
3. Acronyms must be spelled out on first use in each document.
4. Terms are listed alphabetically within each section.

---

## 2. Business & Analytics Terms

---

### Aggregation

**Definition:** The process of combining multiple individual data values into a single summary value. Common aggregation functions include SUM, COUNT, AVERAGE (MEAN), MIN, MAX, and MEDIAN.

**Example:** Aggregating 500 individual sales transactions to produce total monthly revenue.

**In AI Dashboard Generator:** The analysis engine automatically applies appropriate aggregations to numeric columns when generating KPIs and charts. For example, a `Revenue` column will be SUM-aggregated; a `Rating` column will be AVERAGE-aggregated.

**Related Terms:** Dimension, Measure, KPI

---

### Benchmark

**Definition:** A reference point or standard against which performance can be measured. Benchmarks may be internal (e.g., last month's figures) or external (e.g., industry average).

**Example:** "Our gross margin of 38% is 4 percentage points below the industry benchmark of 42%."

**In AI Dashboard Generator:** In V2.0+, the AI will suggest industry benchmarks where available to contextualise metric performance.

---

### CAC (Customer Acquisition Cost)

**Definition:** The total cost of acquiring one new customer, calculated as total marketing and sales spend divided by the number of new customers in a period.

$$\text{CAC} = \frac{\text{Total Sales \& Marketing Spend}}{\text{Number of New Customers}}$$

**Example:** If a company spends £50,000 on marketing and acquires 500 customers, CAC = £100.

**Related Terms:** LTV, ARPU, Unit Economics

---

### Churn Rate

**Definition:** The percentage of customers who cancel or do not renew their subscription in a given period.

$$\text{Monthly Churn Rate} = \frac{\text{Customers Lost in Month}}{\text{Customers at Start of Month}} \times 100$$

**Example:** If 10 out of 200 subscribers cancel in a month, churn rate = 5%.

**In AI Dashboard Generator:** Churn rate is automatically calculated when subscription or renewal data is detected in an uploaded dataset.

---

### Confidence Interval

**Definition:** A range of values within which the true population parameter is expected to fall with a specified probability (e.g., 80% or 95%). Used in forecasting to express uncertainty.

**Example:** "Revenue forecast for Q3 is £850,000 with a 95% confidence interval of £780,000–£920,000."

**In AI Dashboard Generator:** All forecasts display 80% and 95% confidence bands as shaded areas on forecast charts.

**Related Terms:** Forecast, Confidence Score

---

### Confidence Score

**Definition:** A value between 0–100% (or 0–1) that expresses how certain the AI system is about a specific output — whether an insight, recommendation, or forecast.

**Display:** Shown as a colour-coded badge:
- 🟢 Green: ≥ 80% — High confidence
- 🟡 Amber: 50–79% — Moderate confidence
- 🔴 Red: < 50% — Low confidence; treat with caution

**Factors affecting confidence:** Sample size, data completeness, consistency of historical patterns, model fit quality.

**In AI Dashboard Generator:** Every AI-generated element (insight, forecast, recommendation, chat response) displays a confidence score. Low confidence triggers a visible warning.

**Related Terms:** Confidence Interval, Data Quality Score

---

### Correlation

**Definition:** A statistical measure of the extent to which two variables change together. Expressed as a correlation coefficient (r) between -1 and +1.

| Value | Meaning |
|-------|---------|
| r = +1 | Perfect positive correlation |
| r = 0 | No correlation |
| r = -1 | Perfect negative correlation |

**Important caveat:** Correlation does not imply causation. Two variables may move together without one causing the other.

**Example:** "Marketing spend and revenue show a strong positive correlation (r = 0.87)."

**In AI Dashboard Generator:** The AI identifies the top 5 significant correlations in the dataset and surfaces them as insights on the Insights tab.

**Related Terms:** Causation, Regression, Scatter Plot

---

### Dashboard

**Definition:** A visual display of key business information, typically including charts, KPI cards, and summary metrics, arranged to provide a rapid overview of performance.

**In AI Dashboard Generator:** A Dashboard is the primary output of an analysis. It consists of multiple tabs: Executive Summary, KPI Dashboard, Insights, Decision Feed, and Forecasts. Dashboards are automatically generated with no user configuration required.

**Related Terms:** KPI, Executive Summary, Insight

---

### Data Quality Score

**Definition:** A single numeric score (0–100) that summarises the completeness, consistency, and reliability of an uploaded dataset.

**Calculation includes:**
- % of missing values across all columns
- % of duplicate rows
- Column type consistency (e.g., are all values in a "Date" column actual dates?)
- Presence of outliers
- Header row detection quality

**Example:** A dataset with 2% missing values, 0 duplicates, and consistent types scores 94/100.

**In AI Dashboard Generator:** The Data Quality Score is displayed on the dashboard and in the upload summary. Analyses with scores below 70 display a prominent warning banner.

**Related Terms:** Missing Values, Outlier, Data Integrity

---

### Dimension

**Definition:** A categorical column in a dataset that is used to segment or filter data. Dimensions describe the context of a measure — they are typically text or date values.

**Examples:** Product Category, Region, Sales Rep Name, Month, Channel.

**Contrast with:** Measure (a numeric value to be aggregated).

**In AI Dashboard Generator:** Dimensions are automatically detected from column types and used to generate segmentation analyses and filters.

**Related Terms:** Measure, Aggregation, Fact Table

---

### Executive Summary

**Definition:** A concise, narrative overview of the key findings from a data analysis, written in plain language for senior decision-makers. It summarises what happened, what is significant, and what requires attention.

**Structure in AI Dashboard Generator:**
1. Opening: single most important headline finding.
2. KPI overview: the 3 most significant metrics with values and trends.
3. Notable patterns: significant trends, growth, or decline.
4. Anomalies: anything materially unusual.
5. Forward-looking statement: forecast or projection.

**Tone:** Second-person, confident, specific. "Your revenue grew 12% in March, driven primarily by Product Line A."

**Related Terms:** Insight, KPI, Dashboard

---

### Fact Table

**Definition:** In data warehousing, a fact table stores quantitative data (measures) about a business process. It typically contains foreign keys to dimension tables and one or more numeric fact columns.

**Example:** A Sales Fact Table might have columns: Date_ID, Product_ID, Region_ID, Revenue, Units_Sold, Discount.

**In AI Dashboard Generator:** The concept is used informally to describe the primary data table in a single-file upload. Multi-file analysis (V1.5+) introduces the distinction between fact and dimension tables formally.

**Related Terms:** Dimension, Measure, Schema

---

### Forecast

**Definition:** A prediction of future metric values based on historical data patterns. Forecasts are probabilistic estimates, not certainties.

**Types used in AI Dashboard Generator:**
- **Trend-based:** Linear extrapolation of a trend.
- **Exponential Smoothing (ETS):** Weighted average that gives more importance to recent data.
- **Seasonal Decomposition:** Identifies and projects seasonal patterns.

**Output format:** Time-series chart with historical actuals (solid line) and forecast (dashed line), overlaid with 80% and 95% confidence bands.

**Related Terms:** Confidence Interval, Confidence Score, Time Series

---

### Gross Margin

**Definition:** The percentage of revenue retained after deducting the cost of goods sold (COGS).

$$\text{Gross Margin \%} = \frac{\text{Revenue} - \text{COGS}}{\text{Revenue}} \times 100$$

**Example:** Revenue = £500K, COGS = £300K. Gross Margin = 40%.

**Related Terms:** Revenue, COGS, Net Margin

---

### Insight

**Definition:** An AI-generated finding about a dataset that identifies a meaningful pattern, anomaly, correlation, or trend — stated in plain language with a supporting chart and a data citation.

**Structure of an Insight Card:**
- Title: concise finding (< 12 words)
- Body: 2–4 sentence explanation in plain English
- Supporting chart: most appropriate visualisation
- Confidence Score: reliability indicator
- Data Citation: column(s) and row range used
- Category: Trend / Anomaly / Correlation / Top Performer / Risk

**Quality Standard:** Every insight must reference a specific value from the dataset. Generic statements ("revenue fluctuated") are not acceptable.

**Related Terms:** Anomaly, Correlation, Trend, Decision Feed

---

### KPI (Key Performance Indicator)

**Definition:** A quantitative measure used to evaluate the success of an organisation, team, or product in meeting its objectives.

**Characteristics of a good KPI:**
- **Specific:** Clearly defined and unambiguous.
- **Measurable:** Quantifiable from available data.
- **Actionable:** Something the business can influence.
- **Relevant:** Directly linked to a business objective.
- **Time-bound:** Measured over a defined period.

**Examples:** Monthly Recurring Revenue (MRR), Customer Churn Rate, Gross Margin %, Units Sold, Average Order Value.

**In AI Dashboard Generator:** KPIs are automatically identified from the dataset using a combination of column name heuristics and statistical significance scoring. At least 3 KPIs are surfaced on the KPI Dashboard tab.

**Related Terms:** Metric, Measure, Dashboard

---

### LTV (Lifetime Value)

**Definition:** The total revenue expected from a single customer over the entire duration of their relationship with the business.

$$\text{LTV} = \text{ARPU} \times \text{Average Customer Lifespan}$$

**Example:** ARPU = £30/month, average customer stays 24 months. LTV = £720.

**In AI Dashboard Generator:** LTV is automatically calculated when subscription revenue data with a churn rate is detected.

**Related Terms:** CAC, Churn Rate, ARPU

---

### Mean (Average)

**Definition:** The arithmetic mean is the sum of all values divided by the count of values. Often used as a measure of central tendency.

$$\bar{x} = \frac{\sum x_i}{n}$$

**Caution:** The mean is sensitive to outliers. A dataset with one extreme value can produce a misleading mean.

**In AI Dashboard Generator:** Mean is one of several statistics used in data quality and insight generation. Outlier-influenced means are flagged with a warning.

**Related Terms:** Median, Outlier, Standard Deviation

---

### Measure

**Definition:** A numeric column in a dataset that represents a quantity to be aggregated. Measures are the "what" of analysis — quantities such as revenue, count, and cost.

**Examples:** Revenue, Units Sold, Cost, Clicks, Hours Worked.

**Contrast with:** Dimension (a categorical descriptor).

**In AI Dashboard Generator:** Measures are automatically detected and used to generate KPI cards, chart axes, and aggregation calculations.

**Related Terms:** Dimension, Aggregation, KPI

---

### Median

**Definition:** The middle value in a sorted list of numbers. For even-count datasets, the average of the two middle values. More robust than mean in the presence of outliers.

**Example:** Dataset: [10, 12, 14, 100, 200]. Mean = 67.2. Median = 14.

**Related Terms:** Mean, Outlier

---

### Metric

**Definition:** Any quantifiable measure used to assess or track performance. Broader than a KPI — all KPIs are metrics, but not all metrics are KPIs.

**Example:** Page views is a metric. If the business tracks it as a key performance indicator against a target, it becomes a KPI.

**Related Terms:** KPI, Measure

---

### MRR (Monthly Recurring Revenue)

**Definition:** The total predictable revenue generated by active subscriptions in a single month.

$$\text{MRR} = \text{Number of Paying Customers} \times \text{Average Monthly Revenue Per Customer}$$

**Related Terms:** ARR (Annual Recurring Revenue), LTV, Churn

---

### Outlier

**Definition:** A data point that is significantly different from the other values in a dataset. Outliers may indicate data entry errors, fraud, exceptional events, or genuinely unusual observations.

**Detection methods used:**
- **IQR method:** A value is an outlier if it falls below Q1 - 1.5×IQR or above Q3 + 1.5×IQR.
- **Z-score method:** A value is an outlier if its Z-score > 3 (more than 3 standard deviations from the mean).

**In AI Dashboard Generator:** Outliers are detected automatically and surfaced as Anomaly-type insights. They are visually highlighted in charts with an annotation.

**Related Terms:** Anomaly, Data Quality Score, IQR

---

### Percentile

**Definition:** A value below which a given percentage of observations fall. The 90th percentile is the value below which 90% of observations lie.

**Example:** p95 response time of 10 seconds means 95% of requests complete within 10 seconds.

**In AI Dashboard Generator:** Used extensively in performance targets (see [02_Product_Requirements.md](02_Product_Requirements.md)).

---

### Period-on-Period Comparison

**Definition:** A comparison of a metric's value in the current period to the same metric in a prior equivalent period (e.g., this month vs last month, Q1 2026 vs Q1 2025).

**Expressed as:** Absolute change (e.g., +£45K) and percentage change (e.g., +12%).

**In AI Dashboard Generator:** Period-on-period comparisons are automatically calculated when a date column is present and used in Trend-type insights and KPI trend indicators.

---

### Recommendation

**See:** Decision Feed, §4 (Product-Specific Terms).

---

### Regression

**Definition:** A statistical technique for modelling the relationship between a dependent variable and one or more independent variables. Used to predict outcomes and quantify the strength of relationships.

**Types:**
- **Linear regression:** Straight-line relationship between two variables.
- **Multiple regression:** Multiple independent variables.
- **Logistic regression:** Binary outcome prediction.

**In AI Dashboard Generator:** Linear regression is used in trend forecasting. Results are presented in plain language without exposing statistical notation.

---

### Revenue

**Definition:** The total income generated by a business from its primary activities before any deductions. Also called "turnover" or "top-line revenue."

**Note:** Revenue ≠ Profit. Revenue is gross income; profit is what remains after costs.

---

### Seasonality

**Definition:** A recurring pattern in data that repeats at regular intervals (weekly, monthly, quarterly, annually). Often driven by predictable external factors such as weather, holidays, or budget cycles.

**Example:** Retail revenue peaks every December; a weekly pattern shows higher sales on Fridays.

**In AI Dashboard Generator:** Seasonal patterns are automatically detected when at least 2 full cycles of historical data are present. Seasonality is reflected in forecasts and surfaced as a Trend-type insight.

**Related Terms:** Forecast, Trend, Time Series

---

### Standard Deviation

**Definition:** A measure of the dispersion or spread of values in a dataset around the mean. A higher standard deviation indicates greater variability.

$$\sigma = \sqrt{\frac{\sum(x_i - \bar{x})^2}{n}}$$

**In AI Dashboard Generator:** Used internally for outlier detection and confidence calculations. Not exposed in primary UI; described in plain language as "typical range."

---

### Time Series

**Definition:** A sequence of data points collected or recorded at successive points in time, typically at uniform intervals.

**Example:** Daily revenue figures for the past 12 months form a time series.

**In AI Dashboard Generator:** When a date column is detected in the uploaded dataset, AI Dashboard Generator treats the data as a time series and enables forecasting, trend analysis, and period-on-period comparisons.

**Related Terms:** Forecast, Seasonality, Trend

---

### Trend

**Definition:** A general direction or pattern of change in a metric over time — upward, downward, or flat.

**In AI Dashboard Generator:** Trend-type insights describe directional movements in key metrics. Each KPI card shows a trend arrow (↑ up, ↓ down, → flat) based on period-on-period comparison.

---

### Unit Economics

**Definition:** The revenue and cost directly attributable to a single unit of a business — typically a single customer or subscription.

**Key metrics:** CAC, LTV, ARPU, Gross Margin per unit.

**Example:** If LTV = £720 and CAC = £90, the LTV:CAC ratio is 8:1, indicating healthy unit economics.

---

## 3. AI & Machine Learning Terms

---

### Anomaly Detection

**Definition:** The automated identification of data points, patterns, or events that deviate significantly from expected behaviour.

**Methods used in AI Dashboard Generator:**
- **IQR (Interquartile Range):** Statistical outlier detection for individual column values.
- **Z-score:** Identifies values that are unusual relative to the column's mean and standard deviation.
- **Isolation Forest:** An ML algorithm for detecting multidimensional anomalies (used in V1.5+).

**Output:** Anomaly insights describe the unusual value, the expected range, and the magnitude of deviation.

---

### Causal Inference

**Definition:** The process of determining whether a change in one variable *caused* a change in another, as opposed to the two merely being correlated.

**Methods:** Difference-in-differences, instrumental variables, regression discontinuity.

**In AI Dashboard Generator:** Causal inference is an experimental feature planned for V1.5. It will attempt to identify causal relationships from observational data, with explicit uncertainty disclosure.

**Caution:** Causal inference from observational data is inherently uncertain. All AI Dashboard Generator causal claims include an explicit disclaimer.

---

### Confidence Score

**See:** §2 Business & Analytics Terms — Confidence Score.

---

### Embedding

**Definition:** A numerical vector representation of text, data, or other content that captures semantic meaning. Embeddings enable similarity comparisons between pieces of content.

**In AI Dashboard Generator:** Column names and values are embedded to enable the AI to understand the semantic meaning of the data (e.g., recognising that "Revenue", "Sales", and "Income" likely refer to similar concepts).

---

### Exponential Smoothing (ETS)

**Definition:** A time-series forecasting method that assigns exponentially decreasing weights to older observations. More recent data points have more influence on the forecast.

**Variants:**
- **Simple ETS:** For data with no trend or seasonality.
- **Holt's method:** Handles trend.
- **Holt-Winters:** Handles both trend and seasonality.

**In AI Dashboard Generator:** ETS is the default forecasting method for time-series data with monthly or quarterly granularity.

---

### Grounding

**Definition:** The process of connecting an AI model's outputs to verifiable source data, preventing hallucination. A grounded response cites the specific rows, columns, and values used to produce the answer.

**In AI Dashboard Generator:** All AI chat responses and insight narratives are grounded — they cite their data source explicitly. The system is designed to prevent the AI from producing figures that do not exist in the uploaded dataset.

**Related Terms:** Hallucination, RAG

---

### Hallucination

**Definition:** The generation of plausible-sounding but factually incorrect output by a language model. In data analysis contexts, hallucination means fabricating numbers or facts not present in the dataset.

**Zero tolerance policy:** AI Dashboard Generator has a zero-tolerance policy for hallucinated figures. All numeric claims must be directly traceable to source data. The system uses grounding and data citation to enforce this.

---

### LLM (Large Language Model)

**Definition:** A type of AI model trained on large corpora of text data that can generate, summarise, and reason over natural language. Examples: GPT-4o, Claude 3.5, Gemini 1.5 Pro.

**In AI Dashboard Generator:** LLMs are used to generate the Executive Summary, insight narratives, recommendation text, and AI chat responses. They are not used for numerical calculation — all numeric analysis is performed by deterministic code; the LLM only generates the human-readable narrative.

---

### NLG (Natural Language Generation)

**Definition:** The process of automatically generating human-readable text from structured data or computational outputs.

**In AI Dashboard Generator:** NLG is used to convert structured analysis outputs (metrics, trends, anomalies, forecasts) into the written narratives found in the Executive Summary and Insight cards.

---

### NLU (Natural Language Understanding)

**Definition:** The AI capability to comprehend and interpret human language input — understanding intent, entities, and context.

**In AI Dashboard Generator:** NLU powers the AI chat, interpreting user questions about their data and mapping them to appropriate data operations (aggregations, filters, comparisons).

---

### RAG (Retrieval-Augmented Generation)

**Definition:** An AI architecture that enhances LLM responses by first retrieving relevant information from a knowledge source (e.g., a document, database, or dataset), then using that retrieved context to generate a grounded response.

**In AI Dashboard Generator:** The AI chat system uses RAG. When a user asks a question, the system retrieves relevant portions of the uploaded dataset, passes them to the LLM as context, and generates a grounded response. This prevents hallucination and ensures responses are tied to actual data.

**Related Terms:** Grounding, Hallucination, Embedding

---

### Semantic Layer

**Definition:** An abstraction layer between raw data and the analytics experience that defines business-friendly names, relationships, hierarchies, and calculations for data fields.

**Example:** Instead of `tbl_txn.rev_amt`, the semantic layer presents "Monthly Revenue."

**In AI Dashboard Generator:** The AI infers a semantic layer automatically from column names, data types, and statistical patterns — without requiring user configuration. In V2.0+, users will be able to review and edit the inferred semantic layer.

---

### Tokenisation

**Definition:** The process of breaking text into smaller units (tokens) for processing by a language model. Tokens roughly correspond to words or word fragments.

**Relevance:** LLM API costs are priced per token. AI Dashboard Generator optimises prompt construction to minimise token usage while maintaining output quality. This is critical to maintaining unit economics (see [02_Product_Requirements.md §17](02_Product_Requirements.md)).

---

## 4. Product-Specific Terms

---

### Analysis

**Definition:** In AI Dashboard Generator, an Analysis is the core product entity. It represents a single upload-and-generate workflow: one uploaded file, one set of AI-generated outputs (Executive Summary, KPIs, Insights, Decision Feed, Forecasts), and one AI chat session.

**Lifecycle:**
1. Created: file uploaded and analysis triggered.
2. Processing: AI analysis engine running.
3. Complete: dashboard available.
4. Archived: hidden from default view but accessible.
5. Deleted: data purged.

**Uniqueness:** Each analysis has a unique URL (`/analysis/{id}`) and can be shared via a link.

---

### Decision Feed

**Definition:** The AI-generated list of prioritised, actionable business recommendations derived from an analysis. Each item in the Decision Feed is a specific, executable recommendation backed by data evidence.

**Structure of a Decision Feed item:**
- Title: imperative action statement (< 15 words)
- Category: Revenue / Cost / Risk / Growth / Operations
- Priority: High / Medium / Low
- Supporting evidence: specific metric, value, and gap
- Estimated impact: monetary or percentage estimate
- Status: Open / Actioned / Dismissed

**Quality requirement:** Every recommendation must cite specific numbers from the dataset. Generic recommendations are not acceptable.

**Uniqueness:** No direct equivalent exists in any competitor product (as of June 2026). See [07_Competitive_Analysis.md](07_Competitive_Analysis.md).

---

### Data Quality Score

**See:** §2 Business & Analytics Terms — Data Quality Score.

---

### Executive Summary

**See:** §2 Business & Analytics Terms — Executive Summary.

---

### Shared Link

**Definition:** A URL generated by AI Dashboard Generator that allows an unauthenticated external viewer to access a read-only version of a specific analysis.

**Properties:**
- Optional expiry: 7 days, 30 days, or never.
- Optional password protection.
- View count tracking.
- Revocable by the analysis owner at any time.
- Read-only: no editing, no chat for external viewers.

---

### Workspace

**Definition:** (V1.1+) A shared environment within AI Dashboard Generator where multiple team members can access, share, and collaborate on analyses. Workspaces have their own member list, roles, and shared analysis library.

**Relationship to plans:**
- Free and Pro plans: single-user workspace.
- Business plan: workspace with up to 10 members.
- Enterprise: unlimited members.

---

## 5. Data Engineering Terms

---

### CSV (Comma-Separated Values)

**Definition:** A plain-text file format for storing tabular data, where each row is a line and each column value is separated by a delimiter (most commonly a comma).

**In AI Dashboard Generator:** CSV is the primary supported file format. The system auto-detects delimiters (comma, semicolon, tab, pipe) and character encoding (UTF-8, Latin-1).

---

### Data Lineage

**Definition:** The documentation of where data came from, how it was transformed, and where it went. Provides traceability and auditability.

**In AI Dashboard Generator:** Partial data lineage is implemented through data citations — every AI output references the source column and row range. Full data lineage tracking is planned for the Enterprise tier.

---

### Data Normalisation

**Definition:** The process of transforming data into a consistent format. In AI Dashboard Generator, this includes:
- Standardising date formats.
- Trimming whitespace from string values.
- Converting currency strings to numeric values.
- Unmerging merged Excel cells.

---

### Data Pipeline

**Definition:** A series of automated processes that move data from a source, transform it, and deliver it to a destination for analysis or storage.

**In AI Dashboard Generator:** The data pipeline for an analysis is:
1. File upload to object storage.
2. Malware scan.
3. File parsing and schema detection.
4. Data quality assessment.
5. Statistical analysis engine.
6. AI narrative generation.
7. Dashboard rendering.

---

### ETL (Extract, Transform, Load)

**Definition:** A data integration process that extracts data from source systems, transforms it into a consistent format, and loads it into a destination for analysis.

**In AI Dashboard Generator:** A lightweight ETL is performed automatically on every uploaded file. Users do not need to perform ETL manually — this is a core feature differentiation.

---

### JSON (JavaScript Object Notation)

**Definition:** A lightweight, human-readable data interchange format. Supported as an import format (V1.1+) and used internally for API responses and data export.

---

### Parquet

**Definition:** A columnar storage file format optimised for analytical workloads. More efficient than CSV for large datasets because only the required columns need to be read.

**In AI Dashboard Generator:** Parquet is supported for Pro+ plan users in V1.1+.

---

### Schema

**Definition:** The structure of a dataset: column names, data types, and relationships. In AI Dashboard Generator, the schema is automatically inferred from the uploaded file.

---

### Tabular Data

**Definition:** Data organised into rows (records) and columns (fields/attributes). AI Dashboard Generator is designed specifically for tabular data. Non-tabular data (free text, images, PDFs with unstructured content) is not supported in MVP.

---

### XLSX / XLS

**Definition:**
- **XLSX:** The current Microsoft Excel file format (Open XML). Supported in AI Dashboard Generator MVP.
- **XLS:** The legacy binary Excel format (Excel 97–2003). Supported in AI Dashboard Generator MVP (automatically converted to XLSX for processing).

---

## 6. UX & Product Terms

---

### Empty State

**Definition:** The UI state displayed when there is no content to show. In AI Dashboard Generator, empty states occur when: no analyses exist, a filter returns no results, or a feature is unavailable for the current data.

**Design rule:** Empty states must never show a blank screen. They must include: an illustration, an explanation of why there is no content, and a clear call-to-action.

---

### MoSCoW Prioritisation

**Definition:** A prioritisation framework used in product management:
- **Must Have:** Non-negotiable; product cannot launch without this.
- **Should Have:** Important but not critical for launch.
- **Could Have:** Desirable; adds value but not essential.
- **Won't Have Yet:** Explicitly deferred to a future iteration.

**In AI Dashboard Generator:** MoSCoW is the primary prioritisation method used in the Feature Roadmap ([06_Feature_Roadmap.md](06_Feature_Roadmap.md)).

---

### NPS (Net Promoter Score)

**Definition:** A customer loyalty metric calculated from a single question: "On a scale of 0–10, how likely are you to recommend this product to a friend or colleague?"

- **Promoters:** Score 9–10.
- **Passives:** Score 7–8.
- **Detractors:** Score 0–6.

$$\text{NPS} = \% \text{Promoters} - \% \text{Detractors}$$

**Target:** NPS > 40 at Month 6. NPS > 55 at Month 12.

---

### Onboarding

**Definition:** The process of introducing a new user to a product and guiding them to their first meaningful experience (often called the "aha moment").

**In AI Dashboard Generator:** Onboarding is limited to 2 screens maximum before the user reaches the product. Every onboarding screen is skippable.

---

### Progressive Disclosure

**Definition:** A UX design principle where only the most relevant information is shown by default; additional detail is revealed progressively as the user requests it.

**In AI Dashboard Generator:** The Executive Summary is shown by default (simple). Chart configuration options are hidden one level down (complex). Advanced settings are in a separate settings area (very complex).

---

### Skeleton Loading

**Definition:** A loading state that shows a placeholder layout (grey boxes in the shape of expected content) instead of a blank screen or spinner. Reduces perceived loading time.

**In AI Dashboard Generator:** Skeleton loading is used during analysis processing and dashboard rendering to reduce perceived wait time.

---

### TTFI (Time to First Insight)

**Definition:** The time elapsed between a user completing a file upload and the dashboard being visible with at least one insight rendered.

**Target:** p95 TTFI ≤ 10 seconds for files ≤ 5 MB.

**Why it matters:** TTFI is the single most important performance metric for product activation. Every second of additional TTFI increases the likelihood of the user abandoning the session.

---

## 7. Security & Compliance Terms

---

### AES-256

**Definition:** Advanced Encryption Standard with a 256-bit key. The industry-standard encryption algorithm for data at rest.

**In AI Dashboard Generator:** All uploaded files and user data are encrypted at rest using AES-256.

---

### CSRF (Cross-Site Request Forgery)

**Definition:** A type of attack where a malicious website causes a user's browser to make an unintended request to a site where the user is authenticated.

**Mitigation:** AI Dashboard Generator uses CSRF tokens on all state-mutating endpoints.

---

### GDPR (General Data Protection Regulation)

**Definition:** The European Union's regulation on data protection and privacy. Also adopted into UK law as UK GDPR post-Brexit.

**Key rights relevant to AI Dashboard Generator:**
- **Article 17 — Right to Erasure:** Users can request deletion of all personal data within 30 days.
- **Article 20 — Data Portability:** Users can export their data in a machine-readable format.
- **Article 25 — Privacy by Design:** Privacy must be built into the product from the start, not added later.

---

### HttpOnly Cookie

**Definition:** A cookie attribute that prevents JavaScript from accessing the cookie, protecting it from Cross-Site Scripting (XSS) attacks.

**In AI Dashboard Generator:** Refresh tokens are stored in HttpOnly cookies to prevent theft via XSS.

---

### JWT (JSON Web Token)

**Definition:** An open standard for securely transmitting information between parties as a compact, signed JSON object. Used for authentication tokens.

**In AI Dashboard Generator:**
- **Access tokens:** Short-lived JWTs (15-minute expiry) used for API authentication.
- **Refresh tokens:** Long-lived tokens (30-day expiry) stored in HttpOnly cookies.

---

### OWASP Top 10

**Definition:** A regularly updated list of the 10 most critical web application security risks, published by the Open Web Application Security Project.

**In AI Dashboard Generator:** All OWASP Top 10 mitigations are implemented and tested before public launch.

---

### PII (Personally Identifiable Information)

**Definition:** Any data that can be used to identify a specific individual. Includes: name, email, phone number, national insurance number, financial account information.

**In AI Dashboard Generator:** PII detection is performed on all uploaded datasets before data is sent to the LLM API. Detected PII is flagged with a warning; users must confirm before processing continues.

---

### RBAC (Role-Based Access Control)

**Definition:** An access control model where permissions are assigned to roles (rather than individual users), and users are assigned to roles.

**In AI Dashboard Generator:** The five roles (Owner, Admin, Analyst, Viewer, Guest) each have a defined permission set. Permissions are enforced at the API layer, not only in the UI.

---

### SOC 2 Type II

**Definition:** A security compliance standard that verifies a company's systems for security, availability, processing integrity, confidentiality, and privacy over a period of time (typically 6–12 months).

**In AI Dashboard Generator:** SOC 2 Type II certification is a target for the Enterprise tier (planned for Month 13+, see [06_Feature_Roadmap.md](06_Feature_Roadmap.md)).

---

### TLS (Transport Layer Security)

**Definition:** A cryptographic protocol that provides end-to-end encryption for data in transit. TLS 1.3 is the current recommended version.

**In AI Dashboard Generator:** All communications between client and server use TLS 1.3 minimum.

---

## 8. Infrastructure & Engineering Terms

---

### Auto-scaling

**Definition:** The automatic adjustment of computing resources (servers, containers) in response to load. Scales up when demand increases; scales down when demand decreases.

**In AI Dashboard Generator:** Auto-scaling groups respond to CPU utilisation and job queue depth metrics within 2 minutes.

---

### CDN (Content Delivery Network)

**Definition:** A geographically distributed network of servers that delivers web content to users from the nearest location, reducing latency.

**In AI Dashboard Generator:** Static assets (JS, CSS, images) and shared dashboard links are served via CDN for low-latency global access.

---

### CI/CD (Continuous Integration / Continuous Deployment)

**Definition:**
- **CI:** Automatically running tests on every code commit to detect integration issues early.
- **CD:** Automatically deploying tested code to production or staging environments.

---

### Core Web Vitals

**Definition:** A set of user-centric performance metrics defined by Google:

| Metric | Target | Meaning |
|--------|--------|---------|
| LCP (Largest Contentful Paint) | < 2.5s | When the main content is visible |
| FID (First Input Delay) | < 100ms | How quickly the page responds to interaction |
| CLS (Cumulative Layout Shift) | < 0.1 | Visual stability during loading |

---

### Job Queue

**Definition:** A system for managing asynchronous background tasks. In AI Dashboard Generator, file analysis jobs are placed in a queue and processed by worker processes.

**Technology:** BullMQ (Redis-backed) or AWS SQS.

**Why it matters:** The queue decouples file upload from analysis processing, enabling horizontal scaling of the analysis engine independently from the web server.

---

### Multi-Tenancy

**Definition:** A software architecture where a single instance of the application serves multiple customers (tenants), with logical isolation between their data.

**In AI Dashboard Generator:** All users share the same application infrastructure but their data is logically isolated. Enterprise customers may request physical isolation (dedicated infrastructure).

---

### Object Storage

**Definition:** A data storage architecture that manages data as objects (files with metadata and a unique identifier), as opposed to a file hierarchy. Examples: AWS S3, Google Cloud Storage, Azure Blob Storage.

**In AI Dashboard Generator:** Uploaded files are stored in tenant-isolated buckets in object storage. Files are not directly accessible via URL — all access is through the application API with authentication.

---

### p95 / p99

**Definition:** The 95th and 99th percentile of a metric distribution. p95 response time of 10 seconds means 95% of requests complete within 10 seconds; only 5% take longer.

**Why not use averages?** Averages hide tail behaviour. A system might have a 1-second average response time but a 30-second p99 — meaning 1% of users experience very poor performance. AI Dashboard Generator targets explicitly are stated in p95 terms.

---

### SLA (Service Level Agreement)

**Definition:** A commitment to a defined level of service quality, typically expressed as uptime percentage or response time target.

**AI Dashboard Generator SLAs:**

| Tier | Uptime SLA |
|------|-----------|
| Free / Pro | 99.9% (< 8.7 hours downtime/year) |
| Business | 99.95% (< 4.4 hours downtime/year) |
| Enterprise | 99.95% + dedicated CSM + incident response SLA |

---

### WAF (Web Application Firewall)

**Definition:** A security layer that filters and monitors HTTP traffic between a web application and the internet, protecting against common web attacks.

**In AI Dashboard Generator:** A WAF (Cloudflare or AWS WAF) is deployed in front of all public-facing endpoints to protect against SQL injection, XSS, and DDoS attacks.

---

### WCAG 2.1 AA

**Definition:** Web Content Accessibility Guidelines version 2.1, Level AA. The internationally recognised standard for web accessibility.

**AI Dashboard Generator target:** All features must pass WCAG 2.1 AA automated and manual testing before release. See [02_Product_Requirements.md §7](02_Product_Requirements.md).
