# 02 — Product Requirements Document

> **Document:** AI Dashboard Generator — PRD  
> **Version:** 1.0  
> **Last Updated:** 2026-06-25  
> **Status:** Approved  
> **Owner:** Product Management  
> **Related Documents:** [01_Vision.md](01_Vision.md), [04_User_Stories.md](04_User_Stories.md)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Business Goals](#2-business-goals)
3. [Functional Requirements](#3-functional-requirements)
4. [Non-Functional Requirements](#4-non-functional-requirements)
5. [Performance Requirements](#5-performance-requirements)
6. [Security Requirements](#6-security-requirements)
7. [Accessibility Requirements](#7-accessibility-requirements)
8. [Scalability Requirements](#8-scalability-requirements)
9. [File Upload Requirements](#9-file-upload-requirements)
10. [Supported File Types](#10-supported-file-types)
11. [User Roles](#11-user-roles)
12. [Subscription Plans](#12-subscription-plans)
13. [Future Features](#13-future-features)
14. [Out-of-Scope Features](#14-out-of-scope-features)
15. [Success Criteria](#15-success-criteria)
16. [Assumptions](#16-assumptions)
17. [Constraints](#17-constraints)

---

## 1. Overview

### 1.1 Product Summary

AI Dashboard Generator is a web-based SaaS platform that transforms uploaded business data files into fully automated executive dashboards, AI-generated insights, forecasts, recommendations, and an interactive AI chat interface — with zero user configuration required.

### 1.2 Scope

This PRD covers the **MVP through Version 1.0** of AI Dashboard Generator. Features beyond V1.0 are documented in the roadmap ([06_Feature_Roadmap.md](06_Feature_Roadmap.md)) but are not specified here.

### 1.3 Intended Readership

- Engineering (Frontend, Backend, AI/ML)
- QA & Testing
- Product Management
- UX Design
- DevOps / Platform Engineering

---

## 2. Business Goals

| ID | Goal | Metric | Target |
|----|------|--------|--------|
| BG-01 | Acquire paying customers in the first 90 days post-launch | Paying users | ≥ 200 |
| BG-02 | Establish product-market fit | NPS | ≥ 40 at Day 90 |
| BG-03 | Achieve sustainable unit economics | LTV:CAC ratio | ≥ 3:1 by Month 6 |
| BG-04 | Drive viral adoption through shareable outputs | Dashboard share rate | ≥ 20% |
| BG-05 | Establish category leadership for "AI-native BI" | Share of voice in target keywords | Top 5 by Month 12 |
| BG-06 | Reduce support cost through self-service AI | Support tickets per 100 users/week | < 2 |

---

## 3. Functional Requirements

### 3.1 Authentication & Accounts

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-AUTH-01 | Users shall register using email and password | Must Have | Registration form with email, password, confirm password; email validation; strength check |
| FR-AUTH-02 | Users shall authenticate via Google OAuth 2.0 | Must Have | "Sign in with Google" button; successful token exchange; account created on first login |
| FR-AUTH-03 | Users shall authenticate via Microsoft OAuth 2.0 | Should Have | "Sign in with Microsoft" button; successful token exchange |
| FR-AUTH-04 | Users shall receive an email verification link on registration | Must Have | Verification email sent within 30s; link expires after 24h; resend available |
| FR-AUTH-05 | Users shall be able to reset their password via email | Must Have | Forgot password link; reset email with time-limited token (1h); confirmation on success |
| FR-AUTH-06 | Sessions shall persist for 30 days with "Remember me" | Should Have | JWT refresh token stored in HttpOnly cookie; 30-day validity |
| FR-AUTH-07 | Users shall be able to delete their account and all associated data | Must Have | Confirmation dialog; data deletion within 30 days; GDPR-compliant |
| FR-AUTH-08 | Multi-factor authentication (MFA) via TOTP app | Should Have | QR code setup; backup codes provided; MFA enforcement optional per workspace |

### 3.2 File Upload

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-UP-01 | Users shall upload files via drag-and-drop or file picker | Must Have | Drop zone visible; file type validated on drop; progress shown |
| FR-UP-02 | System shall validate file type before beginning upload | Must Have | Reject unsupported types with clear error; accepted types listed |
| FR-UP-03 | System shall validate file size before beginning upload | Must Have | Reject files exceeding plan limit; display limit and current file size |
| FR-UP-04 | System shall display real-time upload progress | Must Have | Progress bar with % and MB transferred; cancel button available |
| FR-UP-05 | Users shall be able to name their analysis on upload | Should Have | Optional name field; defaults to filename if blank |
| FR-UP-06 | System shall detect and handle encoding issues gracefully | Must Have | Auto-detect UTF-8, Latin-1; prompt user if ambiguous |
| FR-UP-07 | System shall handle files with merged cells in Excel | Should Have | Merge cell detection; auto-unmerge; notify user of normalisation |
| FR-UP-08 | System shall support multi-sheet Excel uploads | Should Have | Sheet selector; default to first non-empty sheet; allow sheet selection pre-analysis |
| FR-UP-09 | Upload history shall be retained in user's account | Must Have | Sorted by date; filterable; re-analysis from previous upload available |

### 3.3 Data Processing & Analysis Engine

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-PROC-01 | System shall automatically detect column data types | Must Have | Number, currency, date, boolean, categorical, text; confidence shown; overrideable |
| FR-PROC-02 | System shall detect and report data quality issues | Must Have | Missing values %, duplicate rows, outliers flagged; quality score computed |
| FR-PROC-03 | System shall automatically identify KPIs from the dataset | Must Have | At least 3 KPIs surfaced; sorted by business relevance; each with trend direction |
| FR-PROC-04 | System shall generate at least 5 AI-powered insights per analysis | Must Have | Each insight: title, body text, confidence score, data citation, chart |
| FR-PROC-05 | System shall generate a written Executive Summary | Must Have | 3–5 paragraph narrative; covers top KPIs, significant trends, notable anomalies |
| FR-PROC-06 | System shall produce an anomaly detection report | Must Have | Statistical outliers detected; visualised; described in plain language |
| FR-PROC-07 | System shall produce correlation analysis | Should Have | Top 5 correlations identified; strength and direction described; scatter plots generated |
| FR-PROC-08 | System shall generate time-series forecasts where applicable | Must Have | 3-period ahead forecast where date column exists; confidence interval shown |
| FR-PROC-09 | System shall generate a Decision Feed | Must Have | Minimum 3 prioritised, actionable recommendations per analysis |
| FR-PROC-10 | System shall complete analysis within 10 seconds for files ≤ 5 MB | Must Have | p95 latency ≤ 10s; progress indicator during processing |
| FR-PROC-11 | System shall assign a Data Quality Score to each upload | Should Have | 0–100 score with breakdown by quality dimension |
| FR-PROC-12 | System shall detect the likely business domain from column names | Could Have | Domain tag: e.g. "Sales", "Finance", "HR"; used to prioritise relevant insights |

### 3.4 Dashboard & Visualisation

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-DASH-01 | System shall automatically generate a KPI dashboard view | Must Have | KPI cards with value, trend, % change, sparkline |
| FR-DASH-02 | System shall automatically select appropriate chart types per column combination | Must Have | Bar, line, scatter, pie, area, histogram, heatmap — selection logic documented |
| FR-DASH-03 | Users shall be able to view an Executive Summary tab | Must Have | Rendered as formatted narrative text with inline metrics |
| FR-DASH-04 | Users shall be able to view an Insights tab | Must Have | Insight cards: title, paragraph, confidence badge, supporting chart |
| FR-DASH-05 | Users shall be able to view a Decision Feed tab | Must Have | Prioritised recommendation cards with severity badge (High/Medium/Low) |
| FR-DASH-06 | Users shall be able to view a Forecasts tab | Must Have | Forecast chart with confidence interval; methodology note |
| FR-DASH-07 | Users shall be able to switch between chart types | Should Have | Chart type toggle; selection persists per dashboard |
| FR-DASH-08 | Users shall be able to filter dashboard data by dimension values | Should Have | Filter bar; multi-select; filters apply across all charts |
| FR-DASH-09 | Users shall be able to rename dashboard | Should Have | Inline edit of dashboard name |
| FR-DASH-10 | Dashboards shall be bookmarkable via a unique URL | Must Have | Persistent URL per analysis; requires authentication to view by default |
| FR-DASH-11 | Users shall be able to pin specific insights to the top of the dashboard | Could Have | Pin/unpin toggle; pinned items appear first |

### 3.5 AI Chat

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-CHAT-01 | Users shall be able to ask natural language questions about their data | Must Have | Chat panel accessible from dashboard; freeform text input |
| FR-CHAT-02 | AI shall respond with text and optionally a chart | Must Have | Chart rendered inline in chat; downloadable |
| FR-CHAT-03 | Chat history shall persist per analysis session | Must Have | Full conversation history retained; scrollable |
| FR-CHAT-04 | AI shall cite the specific rows/columns used in its answer | Must Have | Footnote or inline citation with row range and column name |
| FR-CHAT-05 | AI shall handle ambiguous questions gracefully | Must Have | Clarifying question returned rather than hallucinated answer |
| FR-CHAT-06 | Users shall be able to clear chat history | Should Have | "Clear conversation" button; requires confirmation |
| FR-CHAT-07 | System shall suggest follow-up questions proactively | Should Have | 3 suggested follow-up chips shown after each AI response |
| FR-CHAT-08 | Chat responses shall include a confidence indicator | Must Have | Low/Medium/High confidence badge on each AI response |

### 3.6 Export & Sharing

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-EXP-01 | Users shall export analysis as PDF | Must Have | Full dashboard exported; branded; landscape A4 layout |
| FR-EXP-02 | Users shall export analysis as PNG images per chart | Should Have | High-resolution PNG; transparent background option |
| FR-EXP-03 | Users shall export data as CSV | Must Have | Processed/cleaned data exported; original column names preserved |
| FR-EXP-04 | Users shall generate a shareable link to their dashboard | Must Have | Link expires options: 7 days, 30 days, never; password protection option |
| FR-EXP-05 | Shared links shall display a read-only view of the dashboard | Must Have | No edit controls; AI chat disabled on shared view |
| FR-EXP-06 | Users shall export the Executive Summary as a Word document (.docx) | Could Have | Formatted with headings; charts embedded |
| FR-EXP-07 | Users shall export the Decision Feed as a task list to CSV | Could Have | Action, priority, category exported |

### 3.7 Billing & Subscriptions

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-BILL-01 | Users shall be able to subscribe to paid plans via Stripe | Must Have | Stripe Checkout; card, Apple Pay, Google Pay supported |
| FR-BILL-02 | System shall enforce plan limits on upload count and file size | Must Have | Hard block at limit; upgrade prompt shown |
| FR-BILL-03 | Users shall be able to upgrade plans from within the app | Must Have | Upgrade CTA in-app; proration applied |
| FR-BILL-04 | Users shall be able to downgrade plans | Should Have | Downgrade takes effect at next billing cycle; data retained |
| FR-BILL-05 | Users shall receive email receipts for all charges | Must Have | Stripe-generated receipts; branded with AI Dashboard Generator name |
| FR-BILL-06 | Users shall be able to cancel their subscription | Must Have | Cancel flow with exit survey; access continues to end of billing period |
| FR-BILL-07 | System shall provide a 14-day free trial for Pro plan | Must Have | No credit card required for trial; upgrade prompt at day 12 |

### 3.8 Settings

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-SET-01 | Users shall manage profile: name, email, password | Must Have | Profile settings page; email change requires verification |
| FR-SET-02 | Users shall manage notification preferences | Should Have | Email notifications: analysis complete, share activity, billing |
| FR-SET-03 | Users shall view usage metrics against plan limits | Must Have | Uploads used / limit; file size quota; resets on billing cycle |
| FR-SET-04 | Users shall manage connected OAuth accounts | Should Have | Link/unlink Google and Microsoft accounts |
| FR-SET-05 | Users shall configure default currency for analysis | Should Have | ISO 4217 currency selector; applies to all new analyses |

---

## 4. Non-Functional Requirements

| ID | Requirement | Category | Target |
|----|-------------|----------|--------|
| NFR-01 | System availability | Reliability | 99.9% uptime (< 8.7h downtime/year) |
| NFR-02 | Error rate | Reliability | < 0.1% of API requests return 5xx errors |
| NFR-03 | Browser compatibility | Compatibility | Chrome 110+, Firefox 110+, Safari 16+, Edge 110+ |
| NFR-04 | Mobile responsiveness | Compatibility | Full functionality on viewport ≥ 375px width |
| NFR-05 | Internationalisation | i18n | English (en-GB) at launch; i18n framework in place for future localisation |
| NFR-06 | Audit logging | Compliance | All user actions logged with timestamp, user ID, action type |
| NFR-07 | Data retention | Compliance | User data retained for 90 days post-account-deletion before purge |
| NFR-08 | GDPR compliance | Legal | Privacy policy, cookie consent, right to erasure, data portability |
| NFR-09 | Dependency management | Maintainability | No direct use of packages with known critical CVEs; automated Dependabot alerts |
| NFR-10 | Test coverage | Quality | Unit test coverage ≥ 80%; integration test coverage for all critical paths |

---

## 5. Performance Requirements

### 5.1 Response Time Targets

| Operation | p50 Target | p95 Target | p99 Target |
|-----------|-----------|-----------|-----------|
| Page load (initial) | < 1.5s | < 3s | < 5s |
| File upload (5 MB) | < 3s | < 6s | < 10s |
| Analysis completion (≤ 5 MB) | < 5s | < 10s | < 20s |
| Analysis completion (5–50 MB) | < 15s | < 30s | < 60s |
| AI chat response | < 3s | < 6s | < 12s |
| Dashboard render (cold) | < 1s | < 2s | < 4s |
| PDF export | < 5s | < 10s | < 20s |

### 5.2 Throughput Targets

| Metric | Target |
|--------|--------|
| Concurrent analysis jobs | ≥ 100 simultaneous |
| Peak upload throughput | ≥ 500 uploads/hour |
| API request rate | ≥ 1,000 req/s sustained |

### 5.3 Core Web Vitals Targets

| Metric | Target |
|--------|--------|
| Largest Contentful Paint (LCP) | < 2.5s |
| First Input Delay (FID) | < 100ms |
| Cumulative Layout Shift (CLS) | < 0.1 |
| Time to First Byte (TTFB) | < 600ms |

---

## 6. Security Requirements

### 6.1 Authentication & Authorisation

| ID | Requirement |
|----|-------------|
| SEC-01 | Passwords hashed using bcrypt with cost factor ≥ 12 |
| SEC-02 | JWT access tokens expire after 15 minutes; refresh tokens expire after 30 days |
| SEC-03 | Refresh tokens stored in HttpOnly, SameSite=Strict, Secure cookies |
| SEC-04 | All OAuth tokens stored server-side; never exposed to client |
| SEC-05 | Role-based access control (RBAC) enforced at API layer |
| SEC-06 | Account lockout after 10 consecutive failed login attempts (15-minute lockout) |
| SEC-07 | CSRF protection on all state-mutating endpoints |

### 6.2 Data Security

| ID | Requirement |
|----|-------------|
| SEC-08 | All data encrypted at rest using AES-256 |
| SEC-09 | All data encrypted in transit using TLS 1.3 minimum |
| SEC-10 | Uploaded files stored in tenant-isolated object storage (separate S3 bucket per tenant) |
| SEC-11 | Uploaded files are never stored longer than 90 days without user action |
| SEC-12 | User data is never used to fine-tune or train AI models |
| SEC-13 | AI model prompts constructed with strict input sanitisation to prevent prompt injection |
| SEC-14 | All LLM API calls routed through server-side proxy; no client-side API key usage |

### 6.3 Infrastructure Security

| ID | Requirement |
|----|-------------|
| SEC-15 | OWASP Top 10 mitigations implemented and tested at launch |
| SEC-16 | Automated vulnerability scanning in CI/CD pipeline (e.g., Snyk, Trivy) |
| SEC-17 | WAF (Web Application Firewall) in front of all public-facing endpoints |
| SEC-18 | Rate limiting: 100 requests/minute per authenticated user; 20 requests/minute unauthenticated |
| SEC-19 | DDoS protection via CDN provider (Cloudflare or equivalent) |
| SEC-20 | Penetration test completed before public launch; findings remediated |
| SEC-21 | Security incident response plan documented and tested |

### 6.4 Compliance

| ID | Requirement |
|----|-------------|
| SEC-22 | GDPR Article 17 (right to erasure) implemented — deletion within 30 days |
| SEC-23 | GDPR Article 20 (data portability) — full export available in JSON |
| SEC-24 | Cookie consent banner compliant with UK ICO guidance |
| SEC-25 | Sub-processors listed in Privacy Policy; DPA available for enterprise customers |

---

## 7. Accessibility Requirements

| ID | Requirement | Standard |
|----|-------------|----------|
| ACC-01 | All interactive elements reachable via keyboard | WCAG 2.1 AA |
| ACC-02 | Focus indicators visible on all interactive elements | WCAG 2.1 AA |
| ACC-03 | Colour contrast ratio ≥ 4.5:1 for normal text | WCAG 2.1 AA |
| ACC-04 | All images and charts have descriptive alt text | WCAG 2.1 AA |
| ACC-05 | Form inputs have associated labels | WCAG 2.1 AA |
| ACC-06 | Error messages are descriptive and associated with input fields | WCAG 2.1 AA |
| ACC-07 | Screen reader compatibility tested with NVDA and VoiceOver | WCAG 2.1 AA |
| ACC-08 | Animated elements respect `prefers-reduced-motion` | WCAG 2.1 AA |
| ACC-09 | Minimum touch target size 44×44 px on mobile | Apple HIG / Material |
| ACC-10 | Page structure uses semantic HTML5 landmarks | WCAG 2.1 AA |

---

## 8. Scalability Requirements

### 8.1 Architecture Scalability

| ID | Requirement |
|----|-------------|
| SCL-01 | Application must run on horizontally scalable stateless containers |
| SCL-02 | Analysis jobs must be processed via a distributed queue (e.g., BullMQ, SQS) |
| SCL-03 | Database must support read replicas for analytics queries |
| SCL-04 | File storage must be served via CDN for read-heavy operations |
| SCL-05 | Auto-scaling groups must respond to CPU/queue-depth metrics within 2 minutes |

### 8.2 Data Volume Scalability

| Metric | Year 1 Target | Year 3 Target |
|--------|--------------|--------------|
| Total stored analyses | 500K | 50M |
| Daily active analyses | 5K | 200K |
| Stored files (TB) | 5 TB | 500 TB |
| Registered users | 10K | 500K |

### 8.3 Multi-Tenancy

| ID | Requirement |
|----|-------------|
| SCL-06 | Tenant data must be logically isolated at the application layer |
| SCL-07 | Enterprise tenants may request physical data isolation (dedicated infrastructure) |
| SCL-08 | Rate limits must be enforced per tenant to prevent noisy-neighbour degradation |

---

## 9. File Upload Requirements

| ID | Requirement | Detail |
|----|-------------|--------|
| FU-01 | Drag-and-drop upload zone visible on dashboard home and during analysis creation | — |
| FU-02 | Click-to-upload file picker also available | — |
| FU-03 | Maximum file size: Free plan 5 MB, Pro plan 50 MB, Business plan 500 MB | Enforced client-side and server-side |
| FU-04 | Upload progress shown as percentage and bytes transferred | — |
| FU-05 | Failed uploads show actionable error message | Specific: size, format, encoding |
| FU-06 | Malware scanning on all uploads before processing | ClamAV or cloud equivalent |
| FU-07 | Files decompressed before processing if ZIP archive (ZIP containing single supported file) | Limit: one file per ZIP |
| FU-08 | Duplicate upload detection: warn user if file hash matches recent upload | Within 30-day rolling window |
| FU-09 | Upload metadata retained: filename, size, format, upload timestamp, row count, column count | — |
| FU-10 | Users can delete uploaded files and associated analyses | — |

---

## 10. Supported File Types

### 10.1 MVP Supported Formats

| Format | Extension | Max Rows | Notes |
|--------|-----------|----------|-------|
| CSV (UTF-8) | `.csv` | 500,000 | Auto-detect delimiter: comma, semicolon, tab, pipe |
| CSV (Latin-1) | `.csv` | 500,000 | Auto-detected via charset sniffing |
| Excel (xlsx) | `.xlsx` | 250,000 | Multi-sheet; first non-empty sheet default |
| Excel (xls) | `.xls` | 100,000 | Legacy format; auto-converted |

### 10.2 V1.1 Additional Formats

| Format | Extension | Max Rows | Notes |
|--------|-----------|----------|-------|
| Google Sheets | URL | 250,000 | OAuth-linked import |
| JSON (array of objects) | `.json` | 100,000 | Flat array; no nested objects in MVP |
| Parquet | `.parquet` | 1,000,000 | Column-oriented; Pro+ plan |
| TSV | `.tsv` | 500,000 | Tab-separated; treated as CSV variant |

### 10.3 Explicitly Unsupported (MVP)

- PDF with data tables (planned for V1.5)
- SQL database direct connections (planned for V2)
- Word documents
- Image files
- Audio/video files

---

## 11. User Roles

### 11.1 Role Definitions

| Role | Description | Key Permissions |
|------|-------------|----------------|
| **Owner** | Account owner; holds billing relationship | All permissions; manage members; delete workspace |
| **Admin** | Workspace administrator | Manage members; view billing; all analysis permissions |
| **Analyst** | Power user; creates and manages analyses | Create, edit, delete own analyses; share; export |
| **Viewer** | Read-only consumer of analyses | View shared analyses; AI chat; cannot create or edit |
| **Guest** | External user with link-only access | View shared dashboard via link; no login required |

### 11.2 Permission Matrix

| Permission | Owner | Admin | Analyst | Viewer | Guest |
|-----------|-------|-------|---------|--------|-------|
| Upload data | ✅ | ✅ | ✅ | ❌ | ❌ |
| Create analysis | ✅ | ✅ | ✅ | ❌ | ❌ |
| View analysis | ✅ | ✅ | ✅ | ✅ | ✅ (shared only) |
| Edit analysis name | ✅ | ✅ | ✅ (own) | ❌ | ❌ |
| Delete analysis | ✅ | ✅ | ✅ (own) | ❌ | ❌ |
| Share analysis | ✅ | ✅ | ✅ | ❌ | ❌ |
| Export PDF/CSV | ✅ | ✅ | ✅ | ✅ | ❌ |
| Use AI chat | ✅ | ✅ | ✅ | ✅ | ❌ |
| Manage members | ✅ | ✅ | ❌ | ❌ | ❌ |
| Manage billing | ✅ | ❌ | ❌ | ❌ | ❌ |
| Delete workspace | ✅ | ❌ | ❌ | ❌ | ❌ |

---

## 12. Subscription Plans

### 12.1 Plan Overview

| Feature | **Free** | **Pro** (£29/mo) | **Business** (£99/mo) | **Enterprise** (Custom) |
|---------|----------|-----------------|----------------------|------------------------|
| Analyses per month | 5 | 50 | Unlimited | Unlimited |
| Max file size | 5 MB | 50 MB | 500 MB | 5 GB |
| Max rows per file | 10,000 | 250,000 | 1,000,000 | 10,000,000 |
| AI chat messages/month | 20 | 500 | Unlimited | Unlimited |
| AI insights per analysis | 3 | 8 | 15 | Custom |
| Export formats | CSV only | PDF, CSV, PNG | All formats | All + custom branding |
| Shareable links | ❌ | ✅ | ✅ | ✅ |
| Team members | 1 | 1 | Up to 10 | Unlimited |
| Data retention | 30 days | 1 year | 3 years | Custom |
| Forecasting | ❌ | ✅ | ✅ | ✅ |
| Decision Feed | 1 recommendation | 5 recommendations | Unlimited | Unlimited |
| Priority support | ❌ | Email (48h SLA) | Chat (8h SLA) | Dedicated CSM |
| SSO / SAML | ❌ | ❌ | ❌ | ✅ |
| Audit logs | ❌ | ❌ | ✅ | ✅ |
| White-label export | ❌ | ❌ | ❌ | ✅ |
| API access | ❌ | ❌ | ✅ (beta) | ✅ |
| Annual billing discount | — | 20% | 20% | Negotiated |

### 12.2 Free Trial

- Pro plan: 14-day free trial, no credit card required.
- Trial limits: Pro plan limits apply.
- At trial end: automatic downgrade to Free unless card added.
- Trial conversion: in-app prompt at day 12 and day 14.

### 12.3 Overage Policy

- Free plan: hard block at limit; upgrade prompt.
- Pro plan: soft limit; 5 overage analyses/month at £2 each; notification sent.
- Business plan: no overage; soft block with upgrade to Enterprise prompt.

---

## 13. Future Features

Features planned for V1.1 and beyond. Not in scope for MVP.

| Feature | Target Version | Description |
|---------|---------------|-------------|
| Team workspaces | V1.1 | Shared analysis library for multiple users |
| Commenting on insights | V1.1 | Threaded comments on any chart or insight card |
| Scheduled report delivery | V1.5 | Email digest of dashboard on a recurring schedule |
| Native Google Sheets connector | V1.1 | Import directly from linked Google Sheets |
| Salesforce connector | V2.0 | Connect CRM data for revenue analytics |
| Multi-file analysis | V1.5 | Upload two related datasets; AI joins and analyses |
| Custom branding on exports | Enterprise | Company logo, colour scheme on PDF exports |
| Embedded analytics (iFrame) | Enterprise | Embed dashboards in external web properties |
| API for programmatic upload | V2.0 | REST API for automated data pipelines |
| Audit logs | Business V1 | Full event log for compliance and security review |
| SAML 2.0 SSO | Enterprise | Identity provider integration |

---

## 14. Out-of-Scope Features (MVP)

The following features are explicitly not included in MVP and must not be built:

| Feature | Reason |
|---------|--------|
| Direct database connections (SQL) | Complexity; security surface; post-MVP |
| Custom formula/DAX builder | Contradicts zero-config philosophy; power users not primary target |
| Real-time streaming data | Infrastructure cost; not a PMF priority |
| Mobile native apps (iOS/Android) | Web-first approach; responsive web sufficient |
| On-premise deployment | Enterprise feature; requires separate infrastructure |
| Custom ML model training | Scope creep; not viable at MVP stage |
| Data transformation / ETL | Outside core value proposition |
| Collaboration (comments, @mentions) | V1.1 feature |
| White-label/reseller programme | Enterprise feature |
| Custom chart builders | Opinionated auto-selection is core to UVP |

---

## 15. Success Criteria

The MVP is considered successful when all of the following are true:

| Criterion | Threshold | Measurement Method |
|-----------|-----------|-------------------|
| Time to First Insight (p95) | ≤ 10 seconds | Automated performance testing |
| Analysis Success Rate | ≥ 92% of uploads produce a complete dashboard | Application event logs |
| 30-day Activation Rate | ≥ 60% of sign-ups complete first analysis | Product analytics |
| NPS at Day 14 | ≥ 35 | In-app survey (Delighted or equivalent) |
| Zero Critical Security Vulnerabilities at Launch | 0 critical CVEs open | Pre-launch penetration test |
| Core Web Vitals Pass | LCP < 2.5s, CLS < 0.1, FID < 100ms | Lighthouse CI |
| WCAG 2.1 AA Compliance | 0 A/AA violations in automated scan | axe-core in CI |

---

## 16. Assumptions

| ID | Assumption |
|----|------------|
| A-01 | Users have structured tabular data (rows and columns); unstructured text documents are out of scope. |
| A-02 | The majority of MVP users will upload CSV or Excel files; other formats are secondary. |
| A-03 | Users have a basic understanding of their own business data and can identify when an insight is wrong. |
| A-04 | An LLM API (OpenAI GPT-4o or equivalent) will be available and cost-effective for analysis at scale. |
| A-05 | Users consent to temporary data processing by the AI provider under appropriate data processing agreements. |
| A-06 | Stripe is available in all target markets at launch (UK, US, Canada, Australia). |
| A-07 | Users access the product via a modern desktop browser; mobile is secondary at MVP. |
| A-08 | The target user's data does not contain highly sensitive categories (medical, financial PII) in the MVP phase. |

---

## 17. Constraints

| ID | Constraint | Impact |
|----|------------|--------|
| C-01 | LLM inference cost must remain below £0.05 per analysis to maintain unit economics | Prompt optimisation and caching required |
| C-02 | MVP must be deliverable by a team of 3–5 engineers in 12 weeks | Feature scope is tightly controlled |
| C-03 | Must comply with GDPR from day one (EU and UK markets targeted at launch) | Legal review required pre-launch |
| C-04 | AI model responses must not exceed 30 seconds or the user experience degrades unacceptably | Timeout and fallback logic required |
| C-05 | File processing must not expose one tenant's data to another's analysis pipeline | Strict job isolation required |
| C-06 | The product must not require users to install any software beyond a web browser | Full web-based architecture only |
