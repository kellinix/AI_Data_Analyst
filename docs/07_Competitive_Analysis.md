# 07 — Competitive Analysis

> **Document:** AI Dashboard Generator — Competitive Analysis  
> **Version:** 1.0  
> **Last Updated:** 2026-06-25  
> **Status:** Approved  
> **Owner:** Product & Strategy  
> **Related Documents:** [01_Vision.md](01_Vision.md), [06_Feature_Roadmap.md](06_Feature_Roadmap.md)

---

## Table of Contents

1. [Overview & Methodology](#1-overview--methodology)
2. [Power BI](#2-power-bi)
3. [Tableau](#3-tableau)
4. [Looker](#4-looker)
5. [ThoughtSpot](#5-thoughtspot)
6. [ChatGPT Enterprise](#6-chatgpt-enterprise)
7. [Microsoft Copilot](#7-microsoft-copilot)
8. [Claude (Anthropic)](#8-claude-anthropic)
9. [Google Gemini](#9-google-gemini)
10. [Rows](#10-rows)
11. [Polymer](#11-polymer)
12. [Quadratic](#12-quadratic)
13. [Competitive Summary Matrix](#13-competitive-summary-matrix)
14. [Strategic Positioning](#14-strategic-positioning)
15. [Competitive Moats](#15-competitive-moats)

---

## 1. Overview & Methodology

### 1.1 Purpose

This document provides a detailed analysis of the competitive landscape for AI Dashboard Generator. It is used to:

- Validate our unique value proposition.
- Identify genuine feature gaps we can exploit.
- Inform pricing strategy.
- Anticipate competitive moves.
- Guide messaging and positioning.

### 1.2 Competitor Categories

| Category | Players |
|----------|---------|
| **Traditional BI** | Power BI, Tableau, Looker |
| **AI-Native BI** | ThoughtSpot |
| **AI Assistants (Data Capable)** | ChatGPT Enterprise, Microsoft Copilot, Claude, Gemini |
| **Modern Spreadsheet / Collaborative Tools** | Rows, Quadratic |
| **Auto-BI / AI Data Tools** | Polymer |

### 1.3 Analysis Framework

Each competitor is analysed on:

- **Strengths** — Where they genuinely excel.
- **Weaknesses** — Structural limitations that we can exploit.
- **Missing Features** — Capabilities our target users need that the competitor does not provide.
- **Pricing** — Current public pricing (as of 2026-06).
- **What we do better** — Our specific advantages over this competitor.
- **Where they outperform us** — Honest assessment of where we are weaker.
- **Market opportunity** — The gap this creates for AI Dashboard Generator.

---

## 2. Power BI

> **Microsoft Power BI** — Enterprise business intelligence platform with self-service BI capabilities.

### 2.1 Strengths

- Deeply integrated with the Microsoft 365 ecosystem (Excel, SharePoint, Teams, Azure).
- Extensive connector library (300+ data sources).
- Large global community; abundant tutorials and third-party templates.
- Enterprise-grade governance, row-level security, and compliance certifications.
- Power BI Embedded enables embedding analytics in custom applications.
- Relatively affordable for Microsoft enterprise customers via E3/E5 licensing.
- Strong mobile app.
- AI features: Q&A, anomaly detection, smart narratives (limited).

### 2.2 Weaknesses

- **Steep learning curve:** DAX formula language is complex and poorly documented for beginners. Time-to-first-meaningful-dashboard: 4–12 hours for a non-technical user.
- **Desktop-first:** Power BI Desktop is a Windows-only application; authoring is not fully web-native.
- **AI is bolted on:** Smart Narratives and Q&A are add-ons, not core to the experience.
- **No automated analysis:** User must define all calculations and relationships; no zero-configuration mode.
- **Power Query complexity:** Data transformation requires learning M language.
- **Performance degradation at scale:** DirectQuery mode is slow on large datasets without premium capacities.
- **Expensive for standalone use:** £8.40/user/month (Pro) or £16.90/user/month (Premium Per User). Microsoft 365 Fabric adds significant cost.
- **Export limitations:** PDF and PowerPoint exports exist but are not polished.
- **Not suitable for non-Microsoft organisations:** Integrating with non-Microsoft tools is cumbersome.

### 2.3 Missing Features

- Zero-configuration dashboard generation.
- Automatic business narrative in plain English.
- Automated decision feed / prioritised recommendations.
- AI-driven insight generation without user configuration.
- Time-to-insight < 10 seconds from upload.

### 2.4 Pricing

| Plan | Price (per user/month) |
|------|----------------------|
| Free | Free (limited features, publish to web blocked) |
| Pro | £8.40 |
| Premium Per User | £16.90 |
| Premium Capacity | From £3,745/month |
| Fabric (full suite) | £19.80+ per CU |

*Note: Premium features require significant additional investment; Power BI is rarely used standalone by enterprises.*

### 2.5 What We Do Better

1. **Zero configuration** — AI Dashboard Generator requires zero setup; Power BI requires DAX, relationships, and data modelling before any meaningful output.
2. **Time to insight** — < 10 seconds vs 4–12 hours for a first useful Power BI dashboard.
3. **AI-native narrative** — Our Executive Summary is a first-class feature; Smart Narratives in Power BI is a secondary add-on with limited quality.
4. **Accessible to non-technical users** — No formula language required; no modelling required.
5. **Decision Feed** — Power BI has no equivalent prioritised recommendation capability.
6. **SaaS simplicity** — No desktop software to install; entirely browser-based.

### 2.6 Where They Outperform Us

- **Data volume:** Power BI Premium handles billions of rows; our MVP targets ≤ 1M rows.
- **Connector depth:** 300+ native connectors vs our file-upload-first approach.
- **Enterprise governance:** Row-level security, sensitivity labels, DLP policies.
- **Custom visuals marketplace:** Thousands of community-built visual components.
- **Microsoft ecosystem integration:** Direct live connections to Teams, SharePoint, Azure.

### 2.7 Market Opportunity

Power BI is over-engineered for the SMB user who just wants to understand their business data. The millions of SMB users who export from Xero, Shopify, or Square into Excel are not Power BI customers — they are our opportunity.

---

## 3. Tableau

> **Tableau (Salesforce)** — Visual analytics platform focused on data discovery and exploration.

### 3.1 Strengths

- Recognised as the industry standard for exploratory data visualisation.
- Visual Query Language (VQL) is powerful and flexible.
- Tableau Public (free) builds a massive user community.
- Deep Salesforce integration (post-acquisition).
- Strong academic and government adoption.
- Tableau Prep for visual data preparation.
- Pulse (AI feature) launched 2024 for automated metric digests.

### 3.2 Weaknesses

- **Cost-prohibitive for SMBs:** £70+/user/month for Tableau Creator makes it inaccessible for teams below 20 people.
- **Setup time:** Average time to first production dashboard: 1–3 days.
- **AI as afterthought:** Tableau Pulse is a separate product; core Tableau has no AI-native analysis.
- **Requires data preparation:** Raw business data cannot be dropped in and analysed without Tableau Prep or pre-processing.
- **Calculated fields complexity:** Intermediate analytics requires custom LOD (Level of Detail) expressions.
- **No automated narrative:** Tableau shows charts; it does not explain what the charts mean.
- **Heavy product:** Not suitable for occasional or casual users.
- **No recommendations engine:** Passive tool — describes data but does not advise.

### 3.3 Missing Features

- Automated AI insights without configuration.
- Executive narrative generation.
- Decision Feed / recommendations.
- Zero-configuration first dashboard.
- SMB-accessible pricing.

### 3.4 Pricing

| Plan | Price (per user/month, annual) |
|------|-------------------------------|
| Tableau Viewer | £12 |
| Tableau Explorer | £35 |
| Tableau Creator | £70 |
| Tableau+ (AI) | £75+ |
| Tableau Cloud | Additional hosting cost |

### 3.5 What We Do Better

1. **Affordability** — At £29/month vs £70+/user, we are 60%+ cheaper for a single user.
2. **No preparation required** — Drop any file and get results; Tableau requires clean, structured data.
3. **AI-native from the ground up** — Our insights are not an add-on layer; they are the product.
4. **Opinionated auto-charts** — Tableau requires the user to build every chart; we build all charts automatically.

### 3.6 Where They Outperform Us

- **Visual depth:** Tableau's chart customisation capabilities are unmatched.
- **Large datasets:** Hyper engine handles multi-billion row datasets.
- **Calculated fields:** Complex business logic expressible without code.
- **Community & templates:** Vast ecosystem of Tableau Public workbooks.

### 3.7 Market Opportunity

Tableau's pricing creates a large underserved segment: professionals who need data analysis but whose organisations will not pay £70/user/month for infrequent use. These users settle for Excel. AI Dashboard Generator is the right product for them.

---

## 4. Looker

> **Looker (Google)** — Semantic layer and enterprise data platform. Looker Studio is the consumer-facing tool.

### 4.1 Strengths

- Deep Google Cloud Platform (GCP) integration (BigQuery native).
- Looker's semantic layer (LookML) provides a governed, reusable data model.
- Looker Studio (formerly Data Studio) is free and connected to Google ecosystem.
- Enterprise-grade data governance.
- API-first design allows embedding and integration.
- Strong for organisations already on GCP.

### 4.2 Weaknesses

- **Developer tool in disguise:** LookML is a proprietary data modelling language; meaningful use requires engineering resource.
- **No self-serve story for business users:** Looker is built for the IT/engineering team to serve business users, not for business users to self-serve.
- **Long deployment timelines:** A typical Looker implementation takes 3–6 months.
- **Expensive:** Looker enterprise contracts typically start at £50K+/year; not SMB-accessible.
- **Looker Studio limitations:** Free Looker Studio lacks AI features, automated insights, and is limited in data connection options.
- **No AI narrative generation.**
- **No recommendations engine.**

### 4.3 Missing Features

- Self-service for non-technical users.
- AI-generated insights and narrative.
- Zero-configuration analysis.
- SMB pricing.
- Decision Feed.

### 4.4 Pricing

| Product | Price |
|---------|-------|
| Looker Studio | Free |
| Looker (Enterprise) | £50K+/year (estimated contract value) |
| Looker Studio Pro | £9/user/month |

### 4.5 What We Do Better

- Everything in the self-service, non-technical user space. Looker is not our competitor for individual users or SMBs.

### 4.6 Where They Outperform Us

- Large-scale enterprise data governance and semantic modelling.
- GCP ecosystem and BigQuery native connectivity.
- Embedded analytics for product teams.

### 4.7 Market Opportunity

Looker's complexity and cost leaves the entire SMB and mid-market segment exposed. Even enterprise organisations have departments and teams that need analytics without going through the IT/Looker pipeline.

---

## 5. ThoughtSpot

> **ThoughtSpot** — AI-powered analytics platform with natural language search for business data.

### 5.1 Strengths

- Natural language search over data was ThoughtSpot's founding innovation.
- Spotter (AI assistant) provides conversational analytics on enterprise data.
- Strong enterprise adoption in financial services, retail, and technology.
- Sage (LLM integration) adds GPT-based query understanding.
- LiveboardAI generates automated insights from connected data.
- Embeddable analytics API.

### 5.2 Weaknesses

- **Enterprise-only pricing:** Starting from £250K+/year; completely inaccessible to SMBs.
- **Requires live data connection:** File upload is not a primary workflow; requires a connected data warehouse (Snowflake, BigQuery, Databricks).
- **IT dependency:** Implementation requires data engineering to set up schema and connections.
- **No automated executive narrative:** LiveboardAI surfaces insights but does not write a structured executive summary.
- **No decision feed:** Insights are surfaced but not prioritised as executable recommendations.
- **Steep onboarding:** Users must learn to frame questions appropriately.

### 5.3 Missing Features

- File-upload-first workflow.
- Automated executive narrative.
- Decision Feed.
- SMB pricing.
- Zero-configuration analysis.

### 5.4 Pricing

| Tier | Estimated Annual Cost |
|------|----------------------|
| ThoughtSpot Cloud | ~£250K+/year |
| Embedded (custom) | Variable |

### 5.5 What We Do Better

- **Accessibility:** We serve users ThoughtSpot's pricing model structurally excludes.
- **File-first workflow:** No data warehouse required.
- **Executive narrative:** We write the analysis; ThoughtSpot shows charts.
- **Decision Feed:** Prioritised recommendations vs passive insight discovery.
- **Zero-configuration:** No query language learning required.

### 5.6 Where They Outperform Us

- Enterprise-grade live data connections to Snowflake, BigQuery, Databricks.
- Natural language search depth (years of investment).
- Enterprise governance and row-level security.

### 5.7 Market Opportunity

ThoughtSpot's pricing is its greatest weakness. The mid-market (50–500 person companies) who want AI-powered analytics but cannot justify £250K/year are a significant opportunity.

---

## 6. ChatGPT Enterprise

> **ChatGPT Enterprise** — OpenAI's enterprise offering with data analysis via Code Interpreter (Advanced Data Analysis).

### 6.1 Strengths

- Advanced Data Analysis (Code Interpreter) generates Python-based charts and analysis from uploaded files.
- GPT-4o's reasoning capability produces high-quality narrative text.
- Widely adopted; most knowledge workers have used ChatGPT.
- No additional software required; browser-native.
- Can generate complex ad-hoc analyses with natural language instructions.
- Custom GPTs allow some level of specialisation.
- Enterprise pricing includes data privacy guarantees.

### 6.2 Weaknesses

- **Ephemeral analysis:** No persistent dashboard. Every session starts fresh; analysis cannot be bookmarked or shared.
- **Not structured output:** Results are chat messages and images, not a structured BI dashboard.
- **No KPI persistence:** There is no ongoing tracking of metrics — each analysis is one-off.
- **No data model:** ChatGPT does not build a reusable understanding of the data structure.
- **Chart quality is inconsistent:** Matplotlib charts are functional but not designed for executive presentation.
- **No forecasting integration:** Forecasting can be prompted but is not automatic or reproducible.
- **No Decision Feed:** Recommendations can be requested but are not automatically generated.
- **No sharing:** Sharing analysis with stakeholders requires copy-paste or screenshot.
- **Error-prone with large files:** Code Interpreter has reliability issues with complex or large CSVs.
- **No subscription-based access control:** Cannot limit what data is accessible.
- **Pricing per user, not per analysis:** £20+/user/month regardless of usage.

### 6.3 Missing Features

- Persistent, shareable dashboards.
- Automated KPI dashboard generation.
- Structured Executive Summary.
- Decision Feed.
- PDF export of branded reports.
- Time-series forecasting with confidence intervals.
- Data-persistent analysis (revisit the same analysis tomorrow).

### 6.4 Pricing

| Tier | Price |
|------|-------|
| ChatGPT Plus | £20/user/month |
| ChatGPT Enterprise | Custom (typically £30–50+/user/month) |
| ChatGPT Team | £25/user/month |

### 6.5 What We Do Better

1. **Persistent dashboards** — Analysis survives the session and can be revisited.
2. **Shareable output** — One-click share link; branded PDF export.
3. **Structured output** — Executive Summary, KPI cards, insight cards are formatted for business consumption.
4. **Automatic analysis** — No prompt engineering required; upload and receive.
5. **Decision Feed** — Prioritised recommendations are automatic, not prompted.
6. **Forecasting** — Time-series forecasts with confidence intervals, automatically generated.

### 6.6 Where They Outperform Us

- **Analytical flexibility:** Code Interpreter can run any Python analysis a user can describe.
- **Open-ended questions:** ChatGPT can handle unstructured, creative analytical requests.
- **Brand recognition:** ChatGPT is a household name; zero sales friction.

### 6.7 Market Opportunity

Millions of people use ChatGPT to analyse data but are frustrated by ephemeral results and poor shareability. AI Dashboard Generator offers what ChatGPT lacks: a product built specifically for business analytics output.

---

## 7. Microsoft Copilot

> **Microsoft Copilot** — AI assistant embedded across Microsoft 365 (Excel, Teams, PowerPoint, Outlook).

### 7.1 Strengths

- Native integration with Excel — Copilot can generate formulas, pivot tables, and charts from natural language.
- Embedded in Teams, Outlook, and PowerPoint — reduces context-switching.
- Leverages the Microsoft Graph (user's full 365 context).
- Enterprise distribution through existing M365 licensing.
- Data stays within the Microsoft tenant — important for compliance-conscious organisations.

### 7.2 Weaknesses

- **M365 dependency:** Requires Microsoft 365 E3/E5 licence; not available standalone.
- **Excel-only BI experience:** Copilot's analytics is confined to Excel's paradigm — spreadsheets and basic charts.
- **No structured dashboard output:** Results are Excel modifications, not a BI dashboard.
- **Quality is inconsistent:** Formula generation often requires correction.
- **No AI-native analysis product:** Copilot is an assistant, not an analytics product.
- **No Executive Summary as a product:** Narrative generation is ad-hoc, not automatic.
- **No Decision Feed.**
- **No time-series forecasting as a feature.**

### 7.3 Missing Features

- Standalone analytics product.
- Automatic dashboard from file upload.
- AI Executive Summary.
- Decision Feed.
- Shareable dashboard links.

### 7.4 Pricing

| Plan | Price |
|------|-------|
| Microsoft Copilot for M365 | £25.00/user/month (requires M365 E3/E5 subscription) |
| Total cost (with M365 E3) | ~£60+/user/month |

### 7.5 What We Do Better

- We are a dedicated analytics product, not an AI assistant bolted onto a productivity suite.
- No M365 dependency.
- Structured, designed output vs Excel modifications.

### 7.6 Where They Outperform Us

- M365 ecosystem integration (existing workflows, data already in Teams/OneDrive).
- Enterprise distribution (procurement is already done at licence level).

### 7.7 Market Opportunity

Copilot is distributed through Microsoft but not actively "used" for analytics — users upgrade their licence but continue to use Excel manually. We can capture users who try Copilot in Excel and find it inadequate for structured business analysis.

---

## 8. Claude (Anthropic)

> **Claude** — Anthropic's AI assistant with strong reasoning and document analysis capabilities.

### 8.1 Strengths

- Excellent at long-form analysis of uploaded documents.
- Can analyse CSV data uploaded as files with high accuracy.
- Constitutional AI approach produces reliable, well-reasoned output.
- 200K+ token context window handles large documents.
- Projects feature allows persistent file context across sessions.

### 8.2 Weaknesses

- **No persistent dashboards:** Same fundamental limitation as ChatGPT.
- **No chart generation:** Claude does not produce visual charts (as of 2026).
- **No structured BI output:** Results are text responses, not structured dashboards.
- **No sharing/export:** No way to share a Claude analysis as a branded document.
- **No Decision Feed.**
- **No forecasting product.**
- **Requires prompt engineering:** Users must know how to ask for what they want.

### 8.3 Missing Features

- Data visualisation.
- Persistent dashboards.
- KPI tracking.
- Forecasting.
- Decision Feed.
- PDF export.

### 8.4 Pricing

| Plan | Price |
|------|-------|
| Claude Free | Free (rate limited) |
| Claude Pro | £18/month |
| Claude Team | £30/user/month |
| Claude Enterprise | Custom |

### 8.5 What We Do Better

- Visual output (charts, dashboards).
- Structured business analysis format.
- Persistent, shareable results.
- Automatic analysis without prompting.

### 8.6 Where They Outperform Us

- Superior reasoning for complex, nuanced text analysis.
- Handles unstructured documents (contracts, reports) that we do not.
- Lower price point for general AI use cases.

---

## 9. Google Gemini

> **Google Gemini** — Google's multi-modal AI assistant with data analysis capabilities in Google Workspace.

### 9.1 Strengths

- Native integration with Google Sheets (Gemini in Sheets).
- Gemini Advanced can analyse uploaded data files.
- Multi-modal: can interpret charts and tables from images.
- Deep Google Workspace integration (Docs, Slides, Gmail).
- Strong natural language capabilities.

### 9.2 Weaknesses

- **Google Sheets only for native analytics:** Gemini in Sheets operates within the spreadsheet paradigm.
- **No persistent dashboard product.**
- **No structured BI output beyond Sheets.**
- **No Decision Feed.**
- **No forecasting as a product.**
- **Inconsistent performance on large CSVs.**
- **No branded export.**

### 9.3 Missing Features

- Standalone analytics product.
- Dashboard generator.
- Decision Feed.
- Forecasting.
- Shareable BI links.

### 9.4 Pricing

| Plan | Price |
|------|-------|
| Gemini Free | Free |
| Gemini Advanced | £18.99/month |
| Google One AI Premium | £18.99/month |
| Gemini for Workspace | £24/user/month |

### 9.5 What We Do Better

- Dedicated analytics product vs AI assistant.
- Automatic dashboard vs assisted spreadsheet.
- Cross-platform (not Google Workspace-dependent).

### 9.6 Where They Outperform Us

- Google Workspace ecosystem integration.
- Multi-modal analysis (images, documents, charts).
- Brand recognition and distribution.

---

## 10. Rows

> **Rows** — AI-powered spreadsheet with built-in data integrations and charting.

### 10.1 Strengths

- Modern, beautiful spreadsheet product with AI-assisted formulas and analysis.
- Built-in data connectors (Salesforce, Stripe, HubSpot, etc.).
- AI Analyst feature generates written summaries of spreadsheet data.
- Collaborative — real-time editing like Google Sheets.
- Clean, professional aesthetic.
- Built-in chart gallery.
- Can publish tables as embeddable web content.

### 10.2 Weaknesses

- **Still a spreadsheet paradigm:** Users must structure their data as a spreadsheet; no automatic analysis from raw upload.
- **No automated KPI detection.**
- **No time-series forecasting as a product feature.**
- **No Decision Feed / recommendations.**
- **AI Analyst is a summarisation tool, not an analysis engine.**
- **Configuration required:** Users define charts and formulas; not zero-config.
- **Limited chart types compared to BI tools.**

### 10.3 Missing Features

- Zero-configuration analysis.
- Automatic KPI dashboard from file upload.
- Forecasting.
- Decision Feed.
- Anomaly detection.
- Executive Summary (structured).

### 10.4 Pricing

| Plan | Price |
|------|-------|
| Free | Limited (3 tables) |
| Pro | £59/month (team) |
| Business | £149/month (team) |

### 10.5 What We Do Better

- Zero-configuration analysis — upload and receive; no spreadsheet skills required.
- Structured BI output vs spreadsheet interface.
- Automated forecasting and anomaly detection.
- Decision Feed.

### 10.6 Where They Outperform Us

- Live data connectors.
- Real-time collaboration on shared spreadsheets.
- Embeddable tables.
- Built-in formula library.

### 10.7 Market Opportunity

Rows is positioned as a "modern spreadsheet" — users still need to know how to use a spreadsheet. Our zero-configuration approach captures users who want analysis but not a spreadsheet tool.

---

## 11. Polymer

> **Polymer** — AI-powered data analysis tool that transforms spreadsheets and CSV files into interactive reports.

### 11.1 Strengths

- Direct competitor to AI Dashboard Generator in concept — file upload → interactive report.
- Supports CSV, Excel, Google Sheets, Airtable.
- Generates charts, tables, and basic insights automatically.
- Interactive filtering and exploration.
- Shareable links.
- No-code — accessible to non-technical users.
- Published reports are visually clean.

### 11.2 Weaknesses

- **No AI narrative / Executive Summary:** Reports are charts and tables; no written interpretation.
- **No AI chat over data.**
- **No Decision Feed.**
- **No time-series forecasting.**
- **Limited AI capability:** Polymer does pattern detection but lacks the AI depth of a GPT-4-class system.
- **Limited analysis depth:** Surface-level visualisations; no anomaly detection, correlation analysis.
- **UX is dated:** The interface lacks the polish of Linear/Notion-quality products.
- **No PDF export that matches professional presentation standards.**
- **Smaller community and ecosystem.**

### 11.3 Missing Features

- AI-generated Executive Summary.
- AI chat over data.
- Decision Feed / recommendations.
- Time-series forecasting.
- Anomaly detection.
- Confidence scores.
- Professional-grade PDF export.

### 11.4 Pricing

| Plan | Price |
|------|-------|
| Free | 100 rows, limited features |
| Starter | £20/month |
| Pro | £60/month |
| Team | £200/month |

### 11.5 What We Do Better

1. **AI depth** — GPT-4-class insights vs Polymer's pattern detection.
2. **Executive narrative** — Written interpretation vs charts only.
3. **AI chat** — Conversational data exploration vs static reports.
4. **Decision Feed** — Prioritised recommendations.
5. **Forecasting** — Time-series projections with confidence intervals.
6. **Design quality** — Linear/Notion-level polish vs dated aesthetic.
7. **Confidence scores** — Transparency on AI reliability.

### 11.6 Where They Outperform Us

- **Time to market:** Polymer is an established product with a user base.
- **Airtable connector:** Native Airtable integration.
- **Lower price for basic use:** £20/month Free tier is more generous.

### 11.7 Market Opportunity

Polymer is the most direct competitor at the product concept level, but its lack of AI depth (no chat, no narrative, no recommendations) leaves significant room for a product that goes much further. Users who try Polymer and find it shallow are our best acquisition opportunity.

---

## 12. Quadratic

> **Quadratic** — AI-powered spreadsheet that supports Python, SQL, and JavaScript alongside a formula interface.

### 12.1 Strengths

- Innovative concept: infinite canvas spreadsheet with embedded code execution.
- Python, SQL, and JavaScript support in cells.
- AI can generate formulas and code from natural language.
- Real-time collaboration.
- Web-native.
- Targets data analysts who want a code-adjacent spreadsheet.

### 12.2 Weaknesses

- **Technical audience only:** Python/SQL capability is a feature for data analysts; not accessible to non-technical users.
- **No automated analysis:** Users must write code or formulas to get results.
- **Not a BI dashboard product:** Output is a spreadsheet/canvas, not a business dashboard.
- **No AI Executive Summary.**
- **No Decision Feed.**
- **No automated forecasting.**
- **Very early stage product:** Limited reliability and feature completeness.

### 12.3 Missing Features

- Non-technical user experience.
- Automatic analysis.
- AI narrative.
- Business dashboard output.
- Decision Feed.
- Forecasting.
- Sharing for business stakeholders.

### 12.4 Pricing

| Plan | Price |
|------|-------|
| Free | Limited |
| Pro | ~£20/month |
| Team | ~£50/month |

### 12.5 What We Do Better

- Everything in the non-technical user segment. Quadratic is a tool for analysts who code.

### 12.6 Where They Outperform Us

- Technical analysis flexibility (code execution).
- Data analyst use case (power user segment).

### 12.7 Market Opportunity

Quadratic and AI Dashboard Generator target very different segments. Where Quadratic targets data analysts who want code in a spreadsheet, we target business professionals who want intelligence without code. There is no direct competitive conflict.

---

## 13. Competitive Summary Matrix

| Capability | AI Dashboard Generator | Power BI | Tableau | Looker | ThoughtSpot | ChatGPT | Copilot | Rows | Polymer |
|-----------|------------------------|----------|---------|--------|-------------|---------|---------|------|---------|
| **Zero-config analysis from file upload** | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ Partial | ❌ | ❌ | ⚠️ Partial |
| **AI Executive Summary** | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ Ad-hoc | ❌ | ⚠️ Basic | ❌ |
| **KPI Dashboard (auto-generated)** | ✅ | ⚠️ Manual | ⚠️ Manual | ⚠️ Manual | ✅ | ❌ | ❌ | ❌ | ⚠️ Basic |
| **AI Insights** | ✅ | ⚠️ Limited | ❌ | ❌ | ✅ | ⚠️ Ad-hoc | ❌ | ❌ | ⚠️ Basic |
| **Decision Feed / Recommendations** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Time-series Forecasting** | ✅ | ⚠️ Add-on | ⚠️ Add-on | ❌ | ❌ | ⚠️ Ad-hoc | ❌ | ❌ | ❌ |
| **Anomaly Detection** | ✅ | ⚠️ Add-on | ❌ | ❌ | ⚠️ Partial | ⚠️ Ad-hoc | ❌ | ❌ | ⚠️ Basic |
| **AI Chat over data** | ✅ | ⚠️ Q&A (limited) | ❌ | ❌ | ✅ | ✅ | ⚠️ Excel only | ❌ | ❌ |
| **Persistent shareable dashboard** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ⚠️ Partial | ✅ |
| **PDF export (branded)** | ✅ | ⚠️ Basic | ⚠️ Basic | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Confidence scores** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Time to first insight** | < 10 seconds | Hours | Hours | Days | Hours | Minutes | Minutes | Minutes | Minutes |
| **SMB-accessible pricing** | ✅ | ⚠️ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ |
| **No technical knowledge required** | ✅ | ❌ | ❌ | ❌ | ⚠️ | ✅ | ⚠️ | ⚠️ | ✅ |

**Legend:** ✅ Full capability | ⚠️ Partial / limited | ❌ Not available

---

## 14. Strategic Positioning

### 14.1 Positioning Statement

> AI Dashboard Generator is the **only** business analytics product that transforms any uploaded data file into a complete, AI-powered executive analysis — including insights, forecasts, recommendations, and conversational AI — in under 10 seconds, with zero configuration.

### 14.2 Category Creation

Rather than positioning against Power BI or Tableau, AI Dashboard Generator creates a new category: **AI-Native Business Intelligence**.

| Category | Definition | Examples |
|----------|-----------|---------|
| Traditional BI | User builds dashboards from data | Power BI, Tableau, Looker |
| Self-Serve BI | User explores data via drag-and-drop | Looker Studio, Metabase |
| AI-Assisted BI | AI helps user build and query | ThoughtSpot, Copilot in Excel |
| **AI-Native BI** | **AI produces complete analysis automatically** | **AI Dashboard Generator** |

### 14.3 Messaging by Competitor Context

| User Context | Our Message |
|--------------|------------|
| "I use Power BI but it takes too long" | "Stop building. Start knowing. Upload your data and receive the analysis in seconds — no formulas, no modelling." |
| "I use ChatGPT for data" | "Get a proper dashboard, not a chat message. AI Dashboard Generator turns your upload into a shareable, branded executive analysis." |
| "I use Polymer" | "Go deeper. Polymer shows you charts. We tell you what they mean, what to do about them, and what's coming next." |
| "I use Excel" | "Excel describes your data. AI Dashboard Generator understands it." |

---

## 15. Competitive Moats

These are the structural advantages that will be difficult for competitors to replicate.

| Moat | Description | Durability |
|------|-------------|-----------|
| **Product design philosophy** | Radical simplicity and zero-configuration are design constraints, not feature flags. Adding complexity would require rebuilding the product from scratch. | High |
| **Decision Feed IP** | The algorithm that identifies and ranks business recommendations is unique; no competitor offers this. It will require significant investment to replicate. | Medium-High |
| **Confidence scoring framework** | Our transparency layer (confidence scores + data citations) builds user trust. Competitors that produce opaque AI outputs cannot easily retrofit this. | Medium |
| **Vertical data intelligence** | As we accumulate data across industries, we can train better domain-specific models that improve insight quality for each vertical. | High (over time) |
| **User habit loop** | Users who establish a weekly "upload → review → act" habit become highly retentive. The moat is the habitual behaviour, not just the product. | High |
| **SMB distribution** | Word-of-mouth from satisfied SMB customers is a low-cost, high-quality acquisition channel. Enterprise BI companies cannot compete here. | High |
