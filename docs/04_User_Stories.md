# 04 — User Stories

> **Document:** AI Dashboard Generator — User Stories  
> **Version:** 1.0  
> **Last Updated:** 2026-06-25  
> **Status:** Approved  
> **Owner:** Product Management  
> **Related Documents:** [02_Product_Requirements.md](02_Product_Requirements.md), [03_User_Personas.md](03_User_Personas.md)

---

## Table of Contents

1. [Overview & Conventions](#1-overview--conventions)
2. [Authentication](#2-authentication)
3. [Uploads](#3-uploads)
4. [Dashboards](#4-dashboards)
5. [Insights](#5-insights)
6. [Reports](#6-reports)
7. [Forecasting](#7-forecasting)
8. [Recommendations (Decision Feed)](#8-recommendations-decision-feed)
9. [Chat](#9-chat)
10. [Export](#10-export)
11. [Billing](#11-billing)
12. [Settings](#12-settings)
13. [Administration](#13-administration)
14. [Team Collaboration](#14-team-collaboration)

---

## 1. Overview & Conventions

### 1.1 Format

All user stories follow the standard format:

> **As a** [persona / role],  
> **I want** [capability or action],  
> **So that** [business value or outcome].

Each story is tagged with:
- **ID** — Unique identifier (domain prefix + number)
- **Persona** — Primary persona from [03_User_Personas.md](03_User_Personas.md)
- **Priority** — MoSCoW: Must Have (MH), Should Have (SH), Could Have (CH)
- **Acceptance Criteria** — Conditions that must be true for the story to be considered done

### 1.2 Total Story Count

| Domain | Stories |
|--------|---------|
| Authentication | 14 |
| Uploads | 19 |
| Dashboards | 22 |
| Insights | 16 |
| Reports | 11 |
| Forecasting | 12 |
| Recommendations | 11 |
| Chat | 17 |
| Export | 13 |
| Billing | 15 |
| Settings | 10 |
| Administration | 9 |
| Team Collaboration | 11 |
| **Total** | **180** |

---

## 2. Authentication

### US-AUTH-01
**As a** new user,  
**I want** to create an account with my email and a password,  
**So that** I can access the platform securely.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Registration form accepts email, password, confirm password.
  - Password must be ≥ 10 characters, contain at least one uppercase, one number, one symbol.
  - Duplicate email shows a clear error: "An account with this email already exists."
  - On success, verification email sent within 30 seconds.

---

### US-AUTH-02
**As a** new user,  
**I want** to sign up using my Google account,  
**So that** I can avoid creating another password.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Continue with Google" button visible on sign-up and login pages.
  - OAuth 2.0 flow completes without error.
  - First-time Google sign-in creates an account automatically.
  - Account email pre-populated from Google profile.

---

### US-AUTH-03
**As a** new user,  
**I want** to sign up using my Microsoft account,  
**So that** I can use my work identity I already have.

- **Priority:** Should Have
- **Persona:** Marcus (CEO), Priya (Finance), Rachel (HR)
- **Acceptance Criteria:**
  - "Continue with Microsoft" button visible on sign-up and login pages.
  - Microsoft OAuth 2.0 flow completes without error.
  - First-time Microsoft sign-in creates an account automatically.

---

### US-AUTH-04
**As a** new user,  
**I want** to verify my email address before accessing the app,  
**So that** the platform can confirm my identity and send important notifications.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Verification email sent on registration within 30 seconds.
  - Email contains a time-limited link (24-hour expiry).
  - Unverified users see a banner prompt but can still access a limited trial view.
  - "Resend verification email" link available.

---

### US-AUTH-05
**As a** returning user,  
**I want** to log in with my email and password,  
**So that** I can access my saved analyses.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Login form accepts email and password.
  - Incorrect credentials show: "Incorrect email or password."
  - Successful login redirects to dashboard home within 1 second.

---

### US-AUTH-06
**As a** returning user,  
**I want** my session to remain active for 30 days if I select "Remember me",  
**So that** I do not have to log in every time I visit.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Remember me" checkbox visible on login.
  - When checked, session persists via secure refresh token for 30 days.
  - When unchecked, session expires at browser close.

---

### US-AUTH-07
**As a** user who has forgotten their password,  
**I want** to reset it via an email link,  
**So that** I can regain access to my account.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Forgot password" link on login page.
  - Reset email sent within 60 seconds.
  - Reset link is single-use and expires after 1 hour.
  - User is redirected to login with success message after password reset.

---

### US-AUTH-08
**As a** security-conscious user,  
**I want** to enable two-factor authentication (2FA) on my account,  
**So that** my account is protected even if my password is compromised.

- **Priority:** Should Have
- **Persona:** Marcus, Priya, Rachel
- **Acceptance Criteria:**
  - TOTP (Time-based One-Time Password) setup via QR code.
  - 10 single-use backup codes generated at setup.
  - 2FA prompt on login after password verification.
  - 2FA can be disabled with password confirmation.

---

### US-AUTH-09
**As a** user,  
**I want** to see a list of my active sessions (devices),  
**So that** I can revoke access from devices I no longer use.

- **Priority:** Could Have
- **Persona:** All
- **Acceptance Criteria:**
  - Session list shows: device type, browser, last active time, IP geolocation.
  - "Sign out" button per session.
  - "Sign out all other sessions" button available.

---

### US-AUTH-10
**As a** user who suspects their account has been compromised,  
**I want** to revoke all active sessions with one click,  
**So that** I can immediately secure my account.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Sign out everywhere" option in security settings.
  - Invalidates all refresh tokens immediately.
  - Confirmation message shown.

---

### US-AUTH-11
**As a** user,  
**I want** my account to be locked after 10 failed login attempts,  
**So that** brute-force attacks are prevented.

- **Priority:** Must Have
- **Persona:** System / Security
- **Acceptance Criteria:**
  - Account locked for 15 minutes after 10 consecutive failed attempts.
  - User notified by email on lockout.
  - Lockout resolves automatically after 15 minutes or via email unlock link.

---

### US-AUTH-12
**As a** user,  
**I want** to delete my account and all my data,  
**So that** I can exercise my GDPR right to erasure.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Delete account" option in settings with two-step confirmation.
  - Data deletion (files, analyses, account) scheduled within 30 days.
  - Confirmation email sent on deletion request.
  - Login disabled immediately after deletion request.

---

### US-AUTH-13
**As an** administrator,  
**I want** to enforce 2FA for all workspace members,  
**So that** our workspace meets our internal security policy.

- **Priority:** Could Have
- **Persona:** Marcus (CEO), Rachel (HR)
- **Acceptance Criteria:**
  - Workspace admin can toggle "Require 2FA" in workspace security settings.
  - Members without 2FA are prompted to set it up on next login.
  - Members who do not complete 2FA setup within 7 days are locked out.

---

### US-AUTH-14
**As a** user,  
**I want** to be automatically logged out after 60 minutes of inactivity,  
**So that** my account is protected on shared devices.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - Inactivity timer of 60 minutes.
  - Warning modal shown at 55 minutes with "Stay logged in" button.
  - If no interaction, session expires and user is redirected to login.

---

## 3. Uploads

### US-UP-01
**As a** user,  
**I want** to upload a data file by dragging and dropping it onto the dashboard,  
**So that** I can start an analysis without navigating a file picker.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Drop zone visible and labelled on dashboard home.
  - Visual hover state activates when file is dragged over zone.
  - File is accepted and upload begins on drop.
  - Unsupported file type triggers inline error message.

---

### US-UP-02
**As a** user,  
**I want** to upload a file using a traditional file picker button,  
**So that** I can upload files in a familiar way.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Upload file" button opens OS file picker.
  - Filtered to supported file types by default.
  - Selected file triggers upload flow.

---

### US-UP-03
**As a** user,  
**I want** to see the progress of my file upload in real time,  
**So that** I know the upload is working and can estimate when it will complete.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Progress bar shows percentage complete.
  - Bytes transferred and total size displayed (e.g., "2.3 MB of 5.0 MB").
  - Upload speed shown (e.g., "1.2 MB/s").
  - Cancel button available during upload.

---

### US-UP-04
**As a** user,  
**I want** to be shown a clear error if my file is too large for my current plan,  
**So that** I know exactly why my upload failed and what to do next.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Error message: "This file (X MB) exceeds your plan limit (Y MB)."
  - Upgrade CTA shown alongside error.
  - Error caught before upload begins (client-side validation).

---

### US-UP-05
**As a** user,  
**I want** to be shown a clear error if I upload an unsupported file type,  
**So that** I understand why it was rejected.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Error identifies the uploaded file type.
  - Supported file types listed in the error or a link to documentation.
  - Error shown inline in the upload zone; upload not attempted.

---

### US-UP-06
**As a** user,  
**I want** to give my analysis a custom name at upload time,  
**So that** I can identify it easily in my analysis history.

- **Priority:** Should Have
- **Persona:** Oliver (Consultant), Amara (Analyst)
- **Acceptance Criteria:**
  - Optional name field shown in upload dialogue.
  - If left blank, name defaults to filename without extension.
  - Name editable after analysis creation.

---

### US-UP-07
**As a** user uploading an Excel file with multiple sheets,  
**I want** to choose which sheet to analyse,  
**So that** I am not stuck with the wrong data.

- **Priority:** Should Have
- **Persona:** Priya (Finance), James (Ops), Amara (Analyst)
- **Acceptance Criteria:**
  - After upload, if multiple sheets detected, sheet selector shown.
  - Sheet names and row counts displayed per sheet.
  - Default selected: first non-empty sheet.
  - User confirms sheet selection before analysis begins.

---

### US-UP-08
**As a** user,  
**I want** the system to automatically detect the encoding of my CSV file,  
**So that** special characters in my data are not corrupted.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - UTF-8 and Latin-1 (ISO-8859-1) detected automatically.
  - If encoding is ambiguous, user is prompted to confirm.
  - Encoding mismatch results in clear warning with preview of problematic characters.

---

### US-UP-09
**As a** user,  
**I want** to see a warning if I upload a file that appears to be a duplicate of a recent upload,  
**So that** I can avoid duplicate analyses.

- **Priority:** Should Have
- **Persona:** Oliver (Consultant), Amara (Analyst)
- **Acceptance Criteria:**
  - File hash compared against uploads within last 30 days.
  - If duplicate detected: "This file looks like [Analysis Name] uploaded on [date]. Proceed anyway?"
  - User can dismiss and continue or navigate to the existing analysis.

---

### US-UP-10
**As a** user,  
**I want** to view a preview of my uploaded data before the analysis begins,  
**So that** I can confirm the correct data was uploaded.

- **Priority:** Should Have
- **Persona:** Priya, Amara, Oliver
- **Acceptance Criteria:**
  - Preview shows first 10 rows of data in a table.
  - Column names, inferred data types shown.
  - "Confirm and analyse" and "Cancel" buttons shown.
  - Preview loads within 2 seconds of upload completion.

---

### US-UP-11
**As a** user,  
**I want** to see a data quality report after my file is processed,  
**So that** I know if there are issues in my data before trusting the analysis.

- **Priority:** Must Have
- **Persona:** Priya, Amara, Oliver
- **Acceptance Criteria:**
  - Data quality score (0–100) shown prominently.
  - Issues listed: missing values (column name + % missing), duplicate rows, type inconsistencies.
  - "View raw data" link available.
  - Analysis proceeds even with quality issues; issues surfaced as warnings, not blockers.

---

### US-UP-12
**As a** user,  
**I want** to cancel an upload that is in progress,  
**So that** I can avoid uploading the wrong file.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Cancel button visible throughout upload.
  - Cancelling aborts the upload and removes any partially stored file.
  - Confirmation not required for cancel (low risk operation).

---

### US-UP-13
**As a** user,  
**I want** to view my upload history,  
**So that** I can re-access previous analyses and see my usage.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Upload history page lists all analyses: name, date, file type, row count, status.
  - Sortable by date (default: newest first), name.
  - Searchable by name.
  - Delete option per analysis.

---

### US-UP-14
**As a** user,  
**I want** to delete an analysis and its associated file,  
**So that** I can manage my storage quota and remove sensitive data.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Delete button per analysis in upload history.
  - Confirmation dialog: "Delete '[Analysis Name]'? This cannot be undone."
  - Analysis and file deleted immediately.
  - Usage quota updated within 30 seconds.

---

### US-UP-15
**As a** Free plan user who has reached my upload limit,  
**I want** to see a clear message explaining I have reached my limit and how to get more uploads,  
**So that** I can decide whether to upgrade.

- **Priority:** Must Have
- **Persona:** Sarah (SMB Owner), Luca (Startup)
- **Acceptance Criteria:**
  - Block message shown on upload attempt.
  - Current month uploads used / total shown.
  - "Upgrade to Pro" CTA prominent.
  - Resets on next billing cycle date visible.

---

### US-UP-16
**As a** user,  
**I want** the system to detect the delimiter in my CSV file automatically,  
**So that** I do not have to specify whether it uses commas, semicolons, or tabs.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Auto-detection of: comma, semicolon, tab, pipe.
  - Correct delimiter detection in ≥ 99% of test cases.
  - If ambiguous, user shown a preview with two delimiter options to confirm.

---

### US-UP-17
**As a** user,  
**I want** to re-run an analysis on a previously uploaded file with updated data,  
**So that** I can refresh my dashboard with the latest figures.

- **Priority:** Should Have
- **Persona:** Sarah, Daniel, Priya
- **Acceptance Criteria:**
  - "Re-upload and refresh" option in analysis menu.
  - New file uploaded; previous analysis preserved as version history.
  - Dashboard updates to reflect new data.
  - Comparison view (new vs previous) optionally shown.

---

### US-UP-18
**As a** user,  
**I want** to upload a ZIP archive containing a single CSV or Excel file,  
**So that** I can upload exported archives without manually extracting them.

- **Priority:** Could Have
- **Persona:** James (Ops), Amara (Analyst)
- **Acceptance Criteria:**
  - ZIP with single supported file accepted.
  - ZIP with multiple files rejected with message: "Please upload a ZIP containing a single CSV or Excel file."
  - Extracted file processed as if uploaded directly.

---

### US-UP-19
**As a** user concerned about data privacy,  
**I want** to see a clear statement about how my uploaded data is handled,  
**So that** I can make an informed decision before uploading sensitive business data.

- **Priority:** Must Have
- **Persona:** Rachel (HR), Priya (Finance)
- **Acceptance Criteria:**
  - Privacy notice visible on upload screen (not buried in footer).
  - Statement: "Your data is encrypted, never sold, and never used to train AI models."
  - Link to full Privacy Policy.

---

## 4. Dashboards

### US-DASH-01
**As a** user,  
**I want** to see a KPI dashboard automatically generated from my data,  
**So that** I can understand the key metrics without configuring anything.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - At least 3 KPI cards generated automatically.
  - Each KPI card shows: metric name, value, trend indicator (up/down/flat), % change.
  - Sparkline chart per KPI where time dimension exists.
  - Dashboard renders within 2 seconds of analysis completion.

---

### US-DASH-02
**As a** user,  
**I want** to see an Executive Summary tab with a written narrative,  
**So that** I can understand the business story without reading charts.

- **Priority:** Must Have
- **Persona:** Marcus, Oliver, Sarah
- **Acceptance Criteria:**
  - Executive Summary rendered as 3–5 paragraph narrative.
  - Contains: headline finding, top KPIs, significant trends, key anomalies.
  - Written in plain English; no jargon.
  - Visible within 10 seconds of upload completion.

---

### US-DASH-03
**As a** user,  
**I want** to navigate between tabs (Summary, KPIs, Insights, Forecasts, Decision Feed),  
**So that** I can explore different aspects of my analysis.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Tab bar visible at top of dashboard.
  - Tab switching is instant (< 200ms).
  - Active tab highlighted clearly.
  - Tab state persists on page refresh.

---

### US-DASH-04
**As a** user,  
**I want** charts to use the most appropriate visualisation type for my data,  
**So that** the data is represented in the clearest possible way.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Time-series data → line chart default.
  - Category comparisons → bar chart default.
  - Distribution → histogram.
  - Proportions (≤ 6 categories) → pie/donut chart.
  - Correlation (two numeric dimensions) → scatter plot.
  - Chart type selection logic documented in engineering spec.

---

### US-DASH-05
**As a** user,  
**I want** to be able to change the chart type for any visualisation,  
**So that** I can view my data in the way that makes most sense to me.

- **Priority:** Should Have
- **Persona:** Amara (Analyst), Oliver (Consultant)
- **Acceptance Criteria:**
  - Chart type picker accessible via icon on each chart.
  - Options: bar, line, area, scatter, pie, table.
  - Selection persists for that dashboard session.
  - Inappropriate chart types greyed out (e.g., pie chart not available for > 10 categories).

---

### US-DASH-06
**As a** user,  
**I want** to filter the dashboard by any categorical dimension,  
**So that** I can focus on a specific segment of my data.

- **Priority:** Should Have
- **Persona:** James, Daniel, Kezia
- **Acceptance Criteria:**
  - Filter bar above dashboard with all categorical column dimensions.
  - Multi-select filter values.
  - Filters apply globally to all charts on the dashboard.
  - Active filters shown as removable chips.
  - "Clear all filters" button available.

---

### US-DASH-07
**As a** user,  
**I want** to filter the dashboard by a date range,  
**So that** I can focus on a specific time period.

- **Priority:** Should Have
- **Persona:** Priya, Daniel, Kezia
- **Acceptance Criteria:**
  - Date range picker visible when dataset contains a date column.
  - Preset ranges: Last 7 days, Last 30 days, Last 90 days, This year, Custom.
  - All time-series charts update to reflect the selected range.

---

### US-DASH-08
**As a** user,  
**I want** to rename my dashboard,  
**So that** I can keep my analysis history organised.

- **Priority:** Should Have
- **Persona:** Oliver, Amara
- **Acceptance Criteria:**
  - Dashboard name shown in header; click to edit.
  - Inline text field; save on Enter or blur.
  - Name limited to 100 characters.
  - Updated name reflected in upload history immediately.

---

### US-DASH-09
**As a** user,  
**I want** to access my dashboard via a unique, bookmarkable URL,  
**So that** I can return to it directly without navigating through the app.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Each analysis has a unique URL: /analysis/{id}.
  - URL accessible only to authenticated account owner by default.
  - URL persists as long as the analysis exists.

---

### US-DASH-10
**As a** user,  
**I want** to see data quality warnings on my dashboard,  
**So that** I understand any limitations in my analysis before making decisions.

- **Priority:** Must Have
- **Persona:** Priya, Amara
- **Acceptance Criteria:**
  - Data quality banner shown at top of dashboard if quality score < 70.
  - Banner summarises key issues (e.g., "32% of rows in 'Revenue' column contain missing values").
  - Dismissible; warning does not block dashboard.

---

### US-DASH-11
**As a** user,  
**I want** the dashboard to be fully responsive and usable on a tablet,  
**So that** I can review my analysis away from my desk.

- **Priority:** Should Have
- **Persona:** Marcus, Oliver
- **Acceptance Criteria:**
  - Dashboard renders correctly at 768px width (iPad landscape).
  - Charts are not truncated.
  - Tab navigation accessible.
  - KPI cards stack in 2-column grid on tablet.

---

### US-DASH-12
**As a** user,  
**I want** to see how many rows and columns my dataset contains,  
**So that** I understand the scale of data underpinning my analysis.

- **Priority:** Should Have
- **Persona:** Amara, Priya
- **Acceptance Criteria:**
  - Dataset metadata shown in a sidebar or dashboard header.
  - Displays: row count, column count, file size, upload date, analysis date.

---

### US-DASH-13
**As a** user,  
**I want** to hover over a data point on a chart and see its exact value,  
**So that** I can read precise figures without needing an export.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Tooltip appears on hover over any data point.
  - Tooltip shows: dimension value, metric value, % change (where applicable).
  - Tooltip styled consistently with dashboard theme.

---

### US-DASH-14
**As a** user,  
**I want** to see a "loading" state with a progress indicator while my analysis is processing,  
**So that** I know the system is working and have a sense of how long it will take.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Skeleton loading state shown immediately after upload.
  - Progress steps shown: "Reading data → Analysing patterns → Generating insights → Building dashboard".
  - Estimated time remaining shown (if > 3 seconds).
  - Full page error state if analysis fails, with retry button and support link.

---

### US-DASH-15
**As a** user,  
**I want** to see a confidence score on each AI-generated element,  
**So that** I know how reliable the AI's analysis is.

- **Priority:** Must Have
- **Persona:** Priya, Amara, Oliver
- **Acceptance Criteria:**
  - Confidence score shown as a badge on every insight card, forecast, and recommendation.
  - Colour-coded: Green (≥ 80%), Amber (50–79%), Red (< 50%).
  - Clicking the badge shows an explanation of how confidence was calculated.

---

### US-DASH-16
**As a** user,  
**I want** the dashboard to update automatically if I re-upload a new version of my file,  
**So that** I always see the most current analysis.

- **Priority:** Should Have
- **Persona:** Sarah, Priya, Daniel
- **Acceptance Criteria:**
  - Dashboard refreshes within 30 seconds of re-upload completion.
  - "Updated [timestamp]" indicator shown.
  - Previous version accessible via version history.

---

### US-DASH-17
**As a** mobile user,  
**I want** to see a simplified mobile dashboard view,  
**So that** I can check key metrics on my phone.

- **Priority:** Should Have
- **Persona:** Marcus, Daniel
- **Acceptance Criteria:**
  - Mobile view (< 768px): KPI cards in single column, Executive Summary visible, charts scrollable.
  - Charts render correctly at 375px width.
  - Navigation accessible via bottom tab bar on mobile.

---

### US-DASH-18
**As a** user,  
**I want** to pin specific insights or charts to the top of my dashboard,  
**So that** the most important information is always visible first.

- **Priority:** Could Have
- **Persona:** Marcus, Daniel, Oliver
- **Acceptance Criteria:**
  - Pin icon on every chart and insight card.
  - Pinned items appear in a "Pinned" section at the top of the dashboard.
  - Up to 5 items can be pinned.
  - Pinned state persists across sessions.

---

### US-DASH-19
**As a** user,  
**I want** to see the primary currency detected in my dataset displayed correctly,  
**So that** financial figures are presented with the correct symbol.

- **Priority:** Must Have
- **Persona:** Priya, Sarah, Marcus
- **Acceptance Criteria:**
  - Currency auto-detected from column names and values.
  - If detected: currency symbol applied (£, $, €).
  - If ambiguous: user prompted to confirm currency.
  - Numeric formatting applied (thousands separators, 2 decimal places for currency).

---

### US-DASH-20
**As a** user,  
**I want** to view a raw data table of my uploaded dataset,  
**So that** I can verify the underlying data behind the charts.

- **Priority:** Should Have
- **Persona:** Priya, Amara
- **Acceptance Criteria:**
  - "Raw Data" tab available in dashboard.
  - Table is paginated (100 rows per page).
  - Columns sortable.
  - Search within table available.

---

### US-DASH-21
**As a** user,  
**I want** to see trend arrows on all KPI cards,  
**So that** I can instantly understand whether each metric is improving or declining.

- **Priority:** Must Have
- **Persona:** Marcus, Sarah, Daniel
- **Acceptance Criteria:**
  - Up arrow (green) for positive trend, down arrow (red) for negative, flat line (grey) for no change.
  - Trend based on comparison to previous equivalent period.
  - Percentage change shown alongside arrow.

---

### US-DASH-22
**As a** user,  
**I want** to see a clear empty state if my dataset contains no analysable numeric data,  
**So that** I understand why no dashboard was generated.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Empty state shown with illustration.
  - Message explains the issue: "Your file contains no numeric columns for analysis."
  - Suggestions provided: "Try a file with sales figures, quantities, or financial data."
  - Option to upload a different file.

---

## 5. Insights

### US-INS-01
**As a** user,  
**I want** to see at least 5 AI-generated insights about my data,  
**So that** I can discover patterns I would not have spotted myself.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Minimum 5 insight cards on Pro plan; 3 on Free plan.
  - Each card: title, 2–4 sentence narrative, confidence score, supporting chart.
  - Insights ranked by business relevance.

---

### US-INS-02
**As a** user,  
**I want** each insight to show the data source it was derived from,  
**So that** I can verify the AI's reasoning.

- **Priority:** Must Have
- **Persona:** Priya, Amara, Oliver
- **Acceptance Criteria:**
  - Each insight shows: column(s) used, row range or aggregation logic.
  - Shown as a collapsible "Data Source" section under the insight.

---

### US-INS-03
**As a** user,  
**I want** the insights to use plain business language,  
**So that** I can share them with non-technical colleagues without explanation.

- **Priority:** Must Have
- **Persona:** Marcus, Sarah, Rachel
- **Acceptance Criteria:**
  - No statistical jargon in primary insight text.
  - Terms like "statistically significant", "p-value", "standard deviation" not used in main copy.
  - Technical details available in collapsible "Methodology" section.

---

### US-INS-04
**As a** user,  
**I want** the system to detect anomalies in my data and surface them as insights,  
**So that** I can investigate unusual patterns.

- **Priority:** Must Have
- **Persona:** James, Priya, Amara
- **Acceptance Criteria:**
  - Anomalies detected using statistical methods (IQR, Z-score, or isolation forest).
  - Each anomaly shown as an insight card with the anomalous value highlighted.
  - Comparison to expected value shown.

---

### US-INS-05
**As a** user,  
**I want** the system to identify significant correlations between columns,  
**So that** I can understand what drives key metrics.

- **Priority:** Should Have
- **Persona:** Kezia, Amara, Oliver
- **Acceptance Criteria:**
  - Top 5 correlations (positive and negative) surfaced.
  - Correlation strength described in plain language ("strongly related", "weakly related").
  - Scatter plot visualisation for each significant correlation.
  - Causality disclaimer included: "Correlation does not imply causation."

---

### US-INS-06
**As a** user,  
**I want** insights to be sorted by business relevance, not statistical significance,  
**So that** the most important findings appear first.

- **Priority:** Must Have
- **Persona:** Marcus, Sarah, Oliver
- **Acceptance Criteria:**
  - Relevance score computed from: metric importance, magnitude of finding, data volume.
  - Default sort: most relevant first.
  - Sort option available: "Most Relevant", "Confidence", "Metric Magnitude".

---

### US-INS-07
**As a** user,  
**I want** to dismiss insights that are not relevant to me,  
**So that** the insights panel shows only what matters.

- **Priority:** Could Have
- **Persona:** All
- **Acceptance Criteria:**
  - Dismiss (×) button on each insight card.
  - Dismissed insights moved to a "Hidden insights" section.
  - Restore option available.

---

### US-INS-08
**As a** user,  
**I want** the system to detect and flag data quality issues as insights,  
**So that** I can address problems before making decisions.

- **Priority:** Must Have
- **Persona:** Priya, Amara
- **Acceptance Criteria:**
  - Missing value insights: "32% of [column] is missing."
  - Duplicate row insight if > 5% duplicates detected.
  - Data quality insights appear in a dedicated "Data Quality" section.

---

### US-INS-09
**As a** user,  
**I want** to provide feedback on an insight ("helpful" or "not helpful"),  
**So that** the system can improve future analyses.

- **Priority:** Could Have
- **Persona:** All
- **Acceptance Criteria:**
  - Thumbs up / thumbs down on each insight.
  - Feedback recorded anonymously.
  - "Not helpful" prompts optional reason: "Wrong data", "Not relevant", "Confusing".

---

### US-INS-10
**As a** user,  
**I want** to see insights that compare current period to previous period,  
**So that** I can understand performance trends over time.

- **Priority:** Must Have
- **Persona:** Marcus, Daniel, Priya
- **Acceptance Criteria:**
  - Period-on-period insights generated when date column exists.
  - Comparison: current period vs prior period (same length).
  - % change and absolute change shown.
  - Visual: dual-bar or line chart comparison.

---

### US-INS-11
**As a** user,  
**I want** to see insights categorised by type (Trend, Anomaly, Correlation, Top Performer, Risk),  
**So that** I can quickly find insights relevant to my immediate question.

- **Priority:** Should Have
- **Persona:** Amara, Oliver
- **Acceptance Criteria:**
  - Category badge visible on each insight card.
  - Filter bar above insights panel with category filter.

---

### US-INS-12
**As a** user,  
**I want** insights to include the numeric magnitude of findings,  
**So that** I can assess their business impact.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Every insight includes: magnitude (e.g., "+£45K revenue"), % change, affected rows/records.

---

### US-INS-13
**As a** user,  
**I want** to see segment-level insights (e.g., by region, product, team),  
**So that** I can understand which segments are driving overall performance.

- **Priority:** Must Have
- **Persona:** James, Daniel, Kezia
- **Acceptance Criteria:**
  - Top and bottom performing segments identified per key metric.
  - Visualised as ranked bar chart.
  - % of total contribution shown per segment.

---

### US-INS-14
**As a** user,  
**I want** the system to identify seasonal patterns in my data,  
**So that** I can plan for predictable busy or slow periods.

- **Priority:** Should Have
- **Persona:** Sarah, Kezia
- **Acceptance Criteria:**
  - Seasonal decomposition performed when ≥ 2 years of data detected.
  - Seasonal pattern insight: "Revenue peaks in December consistently (+34% above annual average)."
  - Visualised as annotated line chart.

---

### US-INS-15
**As a** user,  
**I want** to receive insights about the top-performing items in my dataset,  
**So that** I know what is working well.

- **Priority:** Must Have
- **Persona:** Sarah, Daniel, Oliver
- **Acceptance Criteria:**
  - Top 3 items (products, customers, regions, etc.) by key metric identified.
  - "Top Performers" insight card with ranked list and values.

---

### US-INS-16
**As a** user,  
**I want** to receive insights about the worst-performing items,  
**So that** I know where to focus attention.

- **Priority:** Must Have
- **Persona:** Marcus, James, Daniel
- **Acceptance Criteria:**
  - Bottom 3 items by key metric identified.
  - "Underperformers" insight card with ranked list and values.
  - Paired with the "Top Performers" card for context.

---

## 6. Reports

### US-REP-01
**As a** user,  
**I want** to generate a professionally formatted PDF report of my dashboard,  
**So that** I can share my analysis with stakeholders who do not have access to the app.

- **Priority:** Must Have
- **Persona:** Oliver, Marcus, Priya
- **Acceptance Criteria:**
  - PDF export includes: cover page, executive summary, KPI dashboard, insights, forecasts, decision feed.
  - A4 landscape format.
  - Clean, professional design with no UI chrome.
  - Generated within 10 seconds for dashboards with ≤ 20 charts.

---

### US-REP-02
**As a** user,  
**I want** the PDF report to include my analysis name, date, and page numbers,  
**So that** it is clear and professional when shared.

- **Priority:** Must Have
- **Persona:** Oliver, Priya
- **Acceptance Criteria:**
  - Cover page: analysis name, creation date, page numbers in footer.
  - "Generated by AI Dashboard Generator" in footer.

---

### US-REP-03
**As a** user,  
**I want** to choose which sections to include in my PDF export,  
**So that** I can tailor the report for different audiences.

- **Priority:** Should Have
- **Persona:** Oliver, Marcus
- **Acceptance Criteria:**
  - Section selector before export: Executive Summary, KPIs, Insights, Forecasts, Decision Feed, Raw Data.
  - At least one section required.
  - Selection previewed.

---

### US-REP-04
**As a** user,  
**I want** to export my cleaned data as a CSV file,  
**So that** I can use the processed data in other tools.

- **Priority:** Must Have
- **Persona:** Amara, Priya
- **Acceptance Criteria:**
  - CSV export includes the processed dataset with original column names.
  - Data type normalisation applied (consistent date formats, number formats).
  - Exported within 5 seconds.

---

### US-REP-05
**As a** user,  
**I want** to export individual charts as PNG images,  
**So that** I can insert them into presentations.

- **Priority:** Should Have
- **Persona:** Priya, Oliver, Kezia
- **Acceptance Criteria:**
  - Download PNG icon on each chart.
  - PNG resolution: 2× retina (minimum 1920px wide for large charts).
  - Filename: analysis-name_chart-name.png.

---

### US-REP-06
**As a** user,  
**I want** to export the Executive Summary as a Word document,  
**So that** I can edit it before including it in a client report.

- **Priority:** Could Have
- **Persona:** Oliver (Consultant)
- **Acceptance Criteria:**
  - .docx export of executive summary text.
  - Headings, paragraphs, and bullet points preserved.
  - Charts embedded as images.

---

### US-REP-07
**As a** user,  
**I want** to view a print-friendly version of my dashboard,  
**So that** I can print it if needed.

- **Priority:** Could Have
- **Persona:** All
- **Acceptance Criteria:**
  - Print-optimised CSS applied when printing (no dark background, no UI chrome).
  - Charts scale to fit A4 paper.

---

### US-REP-08
**As a** user,  
**I want** to schedule a regular report to be emailed to me,  
**So that** I receive updated analysis without having to log in.

- **Priority:** Should Have (V1.5)
- **Persona:** Marcus, Sarah, Daniel
- **Acceptance Criteria:**
  - Schedule options: daily, weekly, monthly.
  - Target email address (can be different from account email).
  - Report format: PDF attachment or link to dashboard.
  - Pause and cancel schedule available.

---

### US-REP-09
**As a** user,  
**I want** to export the Decision Feed as a CSV task list,  
**So that** I can import it into my project management tool.

- **Priority:** Could Have
- **Persona:** Marcus, James
- **Acceptance Criteria:**
  - CSV with columns: Recommendation, Priority, Category, Estimated Impact.
  - One row per recommendation.

---

### US-REP-10
**As a** user,  
**I want** a report history showing all previously generated exports,  
**So that** I can re-download them without regenerating.

- **Priority:** Should Have
- **Persona:** Oliver, Priya
- **Acceptance Criteria:**
  - Report history per analysis: date, format, download link.
  - Downloads expire after 7 days; regeneration available.

---

### US-REP-11
**As a** user,  
**I want** to receive an email notification when my report export is ready,  
**So that** I can continue working while it generates.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - For large exports (> 5 seconds), email sent on completion.
  - Email contains: analysis name, direct download link (7-day expiry).

---

## 7. Forecasting

### US-FOR-01
**As a** user whose dataset contains a date column,  
**I want** the system to automatically generate a forecast for my key metrics,  
**So that** I can anticipate future performance.

- **Priority:** Must Have
- **Persona:** Sarah, Daniel, Luca
- **Acceptance Criteria:**
  - Forecast generated for up to 3 periods ahead (days, weeks, or months depending on data granularity).
  - Confidence interval (80% and 95% bands) displayed.
  - Forecast methodology stated (e.g., "Exponential Smoothing", "Linear Trend").

---

### US-FOR-02
**As a** user,  
**I want** the forecast chart to show historical data alongside predicted data,  
**So that** I can visually assess the reliability of the forecast.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Historical data shown as solid line.
  - Forecast shown as dashed line.
  - Confidence bands shown as shaded area.
  - Clear legend distinguishing actual vs forecast.

---

### US-FOR-03
**As a** user,  
**I want** to see a written interpretation of the forecast,  
**So that** I can understand what it means for my business.

- **Priority:** Must Have
- **Persona:** Sarah, Marcus, Daniel
- **Acceptance Criteria:**
  - Narrative: "Based on current trends, revenue is forecast to reach £X in [month]. This represents a [Y]% increase."
  - Risk factors noted: "This forecast assumes seasonal patterns remain consistent."

---

### US-FOR-04
**As a** user,  
**I want** to be informed of the confidence level of each forecast,  
**So that** I know how much to rely on it.

- **Priority:** Must Have
- **Persona:** Priya, Oliver
- **Acceptance Criteria:**
  - Confidence score shown per forecast.
  - Low confidence (< 60%) triggers a warning: "Insufficient historical data for high-confidence forecasting. Treat this forecast as indicative."

---

### US-FOR-05
**As a** user with insufficient historical data for forecasting,  
**I want** to receive a clear explanation of why forecasting is not available,  
**So that** I understand the limitation.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - If < 12 data points in time series: "Forecasting requires at least 12 data points. Your dataset contains [N]. Add more historical data for forecasts."
  - Forecasts tab shows a helpful empty state (not an error).

---

### US-FOR-06
**As a** user,  
**I want** to adjust the forecast horizon (1, 3, 6, 12 periods),  
**So that** I can see both short-term and long-term projections.

- **Priority:** Should Have
- **Persona:** Priya, Luca, Daniel
- **Acceptance Criteria:**
  - Horizon selector: 1 period, 3 periods, 6 periods, 12 periods.
  - Default: 3 periods.
  - Chart re-renders on selection change.
  - Warning shown for long horizons on short datasets.

---

### US-FOR-07
**As a** user,  
**I want** to see multiple forecasted metrics side by side,  
**So that** I can compare how different parts of my business are expected to perform.

- **Priority:** Should Have
- **Persona:** Marcus, Priya
- **Acceptance Criteria:**
  - Up to 3 forecast charts visible on Forecasts tab.
  - Each chart shows a different metric.
  - Metrics auto-selected by relevance; user can swap.

---

### US-FOR-08
**As a** user,  
**I want** the forecast to take into account seasonality if present in my data,  
**So that** predictable seasonal effects are reflected in the projection.

- **Priority:** Should Have
- **Persona:** Sarah, Kezia
- **Acceptance Criteria:**
  - Seasonal decomposition applied to time-series when ≥ 2 years of data.
  - Seasonal component clearly labelled in forecast chart.
  - Methodology note: "Seasonal adjustment applied based on [monthly/quarterly] patterns."

---

### US-FOR-09
**As a** user,  
**I want** to see forecast accuracy metrics for previous periods,  
**So that** I can calibrate how much trust to place in the forecast.

- **Priority:** Could Have
- **Persona:** Priya, Amara
- **Acceptance Criteria:**
  - If prior forecasts exist: MAPE (Mean Absolute Percentage Error) shown.
  - Stated as: "Our forecasts for this dataset type have been accurate to within ±X% on average."

---

### US-FOR-10
**As a** user,  
**I want** to export my forecast data as CSV,  
**So that** I can use it in financial modelling tools.

- **Priority:** Should Have
- **Persona:** Priya, Luca
- **Acceptance Criteria:**
  - CSV contains: date, forecast value, lower confidence bound, upper confidence bound.
  - Export available from Forecasts tab.

---

### US-FOR-11
**As a** user,  
**I want** to see scenario forecasts (optimistic, base, pessimistic),  
**So that** I can plan for a range of outcomes.

- **Priority:** Could Have
- **Persona:** Marcus, Luca, Oliver
- **Acceptance Criteria:**
  - Three scenario lines: optimistic (+1 standard deviation), base, pessimistic (-1 standard deviation).
  - Scenario toggle to show/hide scenarios.

---

### US-FOR-12
**As a** user,  
**I want** the system to alert me if my current data is tracking significantly above or below forecast,  
**So that** I can take action promptly.

- **Priority:** Could Have
- **Persona:** Marcus, Daniel
- **Acceptance Criteria:**
  - If current period value deviates > 15% from forecast: alert card shown on dashboard.
  - Alert text: "[Metric] is tracking [X]% [above/below] forecast for [period]."

---

## 8. Recommendations (Decision Feed)

### US-REC-01
**As a** user,  
**I want** to receive at least 3 prioritised business recommendations based on my data,  
**So that** I can take concrete action on my analysis.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Minimum 3 recommendation cards on Pro plan; 1 on Free plan.
  - Each card: title, action statement, supporting data, priority badge (High/Medium/Low), estimated impact.

---

### US-REC-02
**As a** user,  
**I want** recommendations to be stated as specific, executable actions,  
**So that** I know exactly what to do.

- **Priority:** Must Have
- **Persona:** Marcus, Sarah, Daniel
- **Acceptance Criteria:**
  - Recommendations use imperative language: "Increase marketing spend for [segment]", not "Consider increasing marketing spend."
  - Each recommendation is no longer than 2 sentences.

---

### US-REC-03
**As a** user,  
**I want** each recommendation to show the data evidence that supports it,  
**So that** I can assess whether I agree with the AI's reasoning.

- **Priority:** Must Have
- **Persona:** Priya, Amara, Oliver
- **Acceptance Criteria:**
  - "Why this recommendation?" section per card.
  - Contains: the metric that triggered it, the observed value, the expected value, the gap.

---

### US-REC-04
**As a** user,  
**I want** to mark a recommendation as "actioned",  
**So that** I can track which recommendations I have followed up on.

- **Priority:** Should Have
- **Persona:** Marcus, James, Daniel
- **Acceptance Criteria:**
  - "Mark as actioned" button per recommendation.
  - Actioned items moved to "Completed" section.
  - Actioned state persists.

---

### US-REC-05
**As a** user,  
**I want** to dismiss a recommendation that is not relevant,  
**So that** my Decision Feed stays focused.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - Dismiss (×) button per recommendation.
  - Dismissed items moved to a "Hidden" section.
  - Restore available.

---

### US-REC-06
**As a** user,  
**I want** recommendations to be categorised (Revenue, Cost, Risk, Growth, Operations),  
**So that** I can filter by what is relevant to me right now.

- **Priority:** Should Have
- **Persona:** Marcus, Oliver
- **Acceptance Criteria:**
  - Category badge on each recommendation.
  - Filter bar above Decision Feed.

---

### US-REC-07
**As a** user,  
**I want** the Decision Feed to be prioritised by potential business impact,  
**So that** the most important actions appear first.

- **Priority:** Must Have
- **Persona:** Marcus, Luca
- **Acceptance Criteria:**
  - Recommendations sorted by: estimated impact magnitude × confidence × urgency.
  - Methodology transparent in tooltip.

---

### US-REC-08
**As a** user,  
**I want** to see an estimated impact for each recommendation,  
**So that** I can prioritise them against other work.

- **Priority:** Should Have
- **Persona:** Marcus, Oliver, Luca
- **Acceptance Criteria:**
  - Estimated impact expressed as: monetary (if applicable), percentage improvement, or qualitative (High/Medium/Low).
  - Stated with appropriate uncertainty: "Estimated impact: £5K–£15K revenue increase."

---

### US-REC-09
**As a** user,  
**I want** to export my Decision Feed as a PDF,  
**So that** I can share it in a leadership meeting.

- **Priority:** Should Have
- **Persona:** Marcus, Oliver
- **Acceptance Criteria:**
  - Decision Feed included in PDF export.
  - Each recommendation formatted clearly with priority and supporting data.

---

### US-REC-10
**As a** user,  
**I want** the Decision Feed to surface risk warnings alongside growth opportunities,  
**So that** I see a balanced view of what needs attention.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Risk recommendations visually distinguished from opportunity recommendations.
  - Risk badge colour: red. Opportunity badge: green. Neutral: grey.

---

### US-REC-11
**As a** user,  
**I want** the AI to avoid generic recommendations that apply to any business,  
**So that** the Decision Feed is specific and credible.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Every recommendation references specific column names, values, and figures from the dataset.
  - A recommendation without a data citation is not acceptable.
  - QA process: review 10 random recommendation cards per release for specificity.

---

## 9. Chat

### US-CHAT-01
**As a** user,  
**I want** to ask questions about my data in plain English,  
**So that** I can explore my data without needing to know SQL or formulas.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Chat input visible on dashboard (side panel or floating).
  - Any natural language question accepted.
  - Response includes text and, where appropriate, a chart.

---

### US-CHAT-02
**As a** user,  
**I want** the AI to answer questions about specific metrics,  
**So that** I can get precise figures without looking at charts.

- **Priority:** Must Have
- **Persona:** Marcus, Daniel, Luca
- **Acceptance Criteria:**
  - Questions like "What was total revenue in March?" return a specific figure.
  - Response includes the calculation logic: "Total revenue for March = sum of [Revenue] column where [Date] is between 2026-03-01 and 2026-03-31 = £45,230."

---

### US-CHAT-03
**As a** user,  
**I want** the AI chat to cite which rows and columns it used to answer my question,  
**So that** I can verify the answer is correct.

- **Priority:** Must Have
- **Persona:** Priya, Amara, Oliver
- **Acceptance Criteria:**
  - Every response includes a data citation.
  - Citation format: "Based on [column name], rows [N–M]."
  - Link to view highlighted rows in the raw data table.

---

### US-CHAT-04
**As a** user,  
**I want** the AI to generate a chart in response to a question,  
**So that** I can visualise the answer.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Questions like "Show me revenue by region" trigger a bar chart in the chat response.
  - Chart is interactive (hover tooltips).
  - Chart downloadable as PNG.

---

### US-CHAT-05
**As a** user,  
**I want** the AI to suggest follow-up questions after each response,  
**So that** I can continue exploring my data without having to think of next questions.

- **Priority:** Should Have
- **Persona:** Sarah, Marcus, Rachel
- **Acceptance Criteria:**
  - 3 suggested follow-up question chips appear after each AI response.
  - Clicking a chip sends it as the next question.
  - Suggestions are contextually relevant to the current response.

---

### US-CHAT-06
**As a** user,  
**I want** the AI to ask a clarifying question rather than guess when my question is ambiguous,  
**So that** I receive accurate answers.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - When question is ambiguous, AI responds: "Did you mean [interpretation A] or [interpretation B]?"
  - Clarification options presented as clickable chips.
  - AI does not hallucinate an answer to an ambiguous question.

---

### US-CHAT-07
**As a** user,  
**I want** the chat history to persist across sessions,  
**So that** I can review previous questions and answers.

- **Priority:** Must Have
- **Persona:** Oliver, Amara, Priya
- **Acceptance Criteria:**
  - Full conversation history stored per analysis.
  - Viewable on dashboard re-open.
  - History scrollable; timestamps visible.

---

### US-CHAT-08
**As a** user,  
**I want** to clear my chat history,  
**So that** I can start a fresh conversation.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Clear conversation" button in chat panel.
  - Confirmation dialog: "Clear all messages? This cannot be undone."
  - History deleted immediately.

---

### US-CHAT-09
**As a** user,  
**I want** the AI to handle questions about data it does not have gracefully,  
**So that** I receive a helpful response rather than a hallucinated one.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - If column or data requested is not in the dataset: "I don't have [data type] in your dataset. The available columns are: [list]."
  - AI does not invent data.

---

### US-CHAT-10
**As a** user,  
**I want** the AI to respond within 6 seconds to my questions,  
**So that** the conversation feels natural.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - p95 response time ≤ 6 seconds.
  - Typing indicator shown while AI is thinking.
  - Timeout after 30 seconds with error message and retry button.

---

### US-CHAT-11
**As a** user,  
**I want** to see a confidence indicator on each AI response,  
**So that** I can assess how reliable the answer is.

- **Priority:** Must Have
- **Persona:** Priya, Amara
- **Acceptance Criteria:**
  - Confidence badge per response: High (≥ 80%), Medium (50–79%), Low (< 50%).
  - Low confidence response includes warning: "This answer is based on limited data and may be inaccurate."

---

### US-CHAT-12
**As a** user,  
**I want** to copy an AI response to my clipboard,  
**So that** I can paste it into an email or document.

- **Priority:** Should Have
- **Persona:** Marcus, Oliver
- **Acceptance Criteria:**
  - "Copy" icon per AI response.
  - Text copied to clipboard.
  - Toast notification: "Copied to clipboard."

---

### US-CHAT-13
**As a** user on the Free plan,  
**I want** to be clearly informed when I am approaching my monthly chat message limit,  
**So that** I can plan my usage or decide to upgrade.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Warning shown at 80% of message limit used.
  - Hard block at 100% with upgrade CTA.
  - Messages remaining shown in chat panel header.

---

### US-CHAT-14
**As a** user,  
**I want** to ask the AI to compare two time periods,  
**So that** I can understand what changed and by how much.

- **Priority:** Must Have
- **Persona:** Priya, Daniel, Marcus
- **Acceptance Criteria:**
  - Question: "Compare Q1 vs Q2 revenue" returns a side-by-side comparison.
  - Absolute and percentage differences shown.
  - Bar chart comparison generated.

---

### US-CHAT-15
**As a** user,  
**I want** to ask the AI what its recommendations are,  
**So that** I can receive them in a conversational format.

- **Priority:** Should Have
- **Persona:** Sarah, Marcus
- **Acceptance Criteria:**
  - "What should I do based on this data?" returns a summary of Decision Feed recommendations in chat.
  - Response links to the full Decision Feed tab.

---

### US-CHAT-16
**As a** user,  
**I want** to ask the AI to explain a chart or insight in simpler terms,  
**So that** I can understand something I found confusing.

- **Priority:** Should Have
- **Persona:** Sarah, Rachel
- **Acceptance Criteria:**
  - "Explain this in simple terms" context menu option on any insight card.
  - Opens chat with pre-populated question about the selected insight.
  - AI response uses simpler language than the original insight.

---

### US-CHAT-17
**As a** user,  
**I want** to ask the AI what the most important finding in my data is,  
**So that** I can quickly understand the headline takeaway.

- **Priority:** Must Have
- **Persona:** Marcus, Sarah
- **Acceptance Criteria:**
  - "What's the most important thing in this data?" returns a single, concise finding.
  - Finding includes: metric, value, change direction, and implication.

---

## 10. Export

### US-EXP-01
**As a** user,  
**I want** to export my full dashboard as a PDF,  
**So that** I can share it with stakeholders who do not use the platform.

- **Priority:** Must Have — *see also US-REP-01*
- **Persona:** All
- **Acceptance Criteria:** Same as US-REP-01.

---

### US-EXP-02
**As a** user,  
**I want** to generate a shareable link to my dashboard,  
**So that** I can share it with someone who does not have an account.

- **Priority:** Must Have
- **Persona:** Oliver, Marcus, Kezia
- **Acceptance Criteria:**
  - "Share" button generates a unique link.
  - Link options: expiry (7 days, 30 days, never) and optional password.
  - Shared view is read-only; no editing or chat.
  - Link deactivation available at any time.

---

### US-EXP-03
**As a** recipient of a shared link,  
**I want** to view the dashboard without creating an account,  
**So that** I can quickly review the analysis.

- **Priority:** Must Have
- **Persona:** External stakeholders / Guest
- **Acceptance Criteria:**
  - Shared link opens read-only dashboard without login.
  - "Create account to interact with this data" CTA shown.
  - Password prompt shown if link is password-protected.

---

### US-EXP-04
**As a** user,  
**I want** to export individual charts as PNG images,  
**So that** I can paste them into a presentation.

- **Priority:** Should Have
- **Persona:** Priya, Oliver, Kezia
- **Acceptance Criteria:** Same as US-REP-05.

---

### US-EXP-05
**As a** user,  
**I want** to export my processed data as CSV,  
**So that** I can use it in other tools.

- **Priority:** Must Have
- **Persona:** Amara, Priya
- **Acceptance Criteria:** Same as US-REP-04.

---

### US-EXP-06
**As a** user,  
**I want** the shareable link to reflect the current state of the dashboard,  
**So that** the recipient sees the same analysis I see.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Shared link shows the same dashboard version as when the link was created.
  - If analysis is updated (re-upload), a new link is generated; the old link reflects the previous version.

---

### US-EXP-07
**As a** user,  
**I want** to see how many times my shared link has been viewed,  
**So that** I know whether stakeholders have actually looked at the analysis.

- **Priority:** Could Have
- **Persona:** Oliver, Marcus
- **Acceptance Criteria:**
  - View count displayed per shared link in the "Shares" panel.
  - Timestamp of last view shown.

---

### US-EXP-08
**As a** user,  
**I want** to revoke a shared link,  
**So that** I can remove access to an analysis that is no longer current.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Revoke" button per shared link.
  - Revoked link immediately returns 404 for recipients.
  - Confirmation required.

---

### US-EXP-09
**As a** user,  
**I want** to export my chat conversation as a PDF,  
**So that** I can include the AI analysis session in a report.

- **Priority:** Could Have
- **Persona:** Oliver, Priya
- **Acceptance Criteria:**
  - Chat export includes: question, AI response, supporting charts, citations.
  - Timestamped per message.

---

### US-EXP-10
**As a** user,  
**I want** to be notified by email when someone views my shared dashboard,  
**So that** I know when stakeholders are reviewing the analysis.

- **Priority:** Could Have
- **Persona:** Oliver, Marcus
- **Acceptance Criteria:**
  - Optional email notification per share link.
  - Email: "Your dashboard '[Name]' was viewed [N] minutes ago."
  - Configurable in notification settings.

---

### US-EXP-11
**As a** user,  
**I want** to download a full data package (CSV + PDF + JSON summary),  
**So that** I have a complete offline archive of my analysis.

- **Priority:** Could Have
- **Persona:** Priya, Amara
- **Acceptance Criteria:**
  - "Download all" option produces a ZIP file.
  - Contains: original file, cleaned CSV, PDF report, JSON insight summary.

---

### US-EXP-12
**As a** user,  
**I want** the PDF export to complete within 15 seconds,  
**So that** I do not have to wait a long time for a simple export.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - PDF generated within 10s (p95).
  - Progress spinner shown during generation.
  - Email notification if generation takes longer than 15 seconds.

---

### US-EXP-13
**As a** Business plan user,  
**I want** to export all my analyses in bulk,  
**So that** I can archive or migrate my data.

- **Priority:** Could Have
- **Persona:** Amara, Oliver
- **Acceptance Criteria:**
  - "Export all analyses" option in settings.
  - Produces ZIP with all analysis PDFs and CSVs.
  - Email notification on completion.

---

## 11. Billing

### US-BILL-01
**As a** new user,  
**I want** to start a 14-day free trial of the Pro plan without entering my credit card,  
**So that** I can evaluate the product before committing.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Start free trial" CTA on sign-up.
  - No payment method required.
  - Trial expires after 14 days; user notified at day 12 and day 14.
  - At trial end: automatic downgrade to Free plan.

---

### US-BILL-02
**As a** user who has decided to upgrade,  
**I want** to subscribe to a paid plan using my credit card,  
**So that** I can access more features and uploads.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Stripe Checkout embedded in upgrade flow.
  - Supports: Visa, Mastercard, Amex, Apple Pay, Google Pay.
  - Subscription activates immediately on payment.
  - Welcome email sent on upgrade.

---

### US-BILL-03
**As a** paying user,  
**I want** to receive an email receipt for every charge,  
**So that** I have a record for my accounts.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Stripe-generated receipt emailed within 5 minutes of charge.
  - Receipt includes: amount, date, plan name, last 4 digits of card.

---

### US-BILL-04
**As a** user,  
**I want** to view my billing history in-app,  
**So that** I can review past charges without checking my email.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - Billing history page: date, amount, status, download invoice PDF.
  - Last 24 months of history shown.

---

### US-BILL-05
**As a** user,  
**I want** to update my payment method,  
**So that** I can keep my subscription active if my card changes.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Update card" option in billing settings.
  - Stripe's secure card update form used.
  - New card validated before old card removed.

---

### US-BILL-06
**As a** user,  
**I want** to upgrade my plan at any time,  
**So that** I can access more features immediately.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Upgrade" button accessible from in-app usage limit messages and settings.
  - Proration applied: user charged difference for remainder of billing period.
  - Upgrade takes effect immediately.

---

### US-BILL-07
**As a** user,  
**I want** to downgrade my plan,  
**So that** I can reduce costs if I no longer need premium features.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - Downgrade takes effect at start of next billing cycle.
  - User warned which features they will lose.
  - Data retained for 90 days after downgrade; not deleted immediately.

---

### US-BILL-08
**As a** user,  
**I want** to cancel my subscription,  
**So that** I do not continue to be billed if I am not using the service.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Cancel subscription" in billing settings.
  - Exit survey offered (optional, not blocking).
  - Access continues until end of current billing period.
  - Confirmation email sent with access end date.

---

### US-BILL-09
**As a** user on a paid plan,  
**I want** to receive a warning email before my subscription renews,  
**So that** I am not surprised by the charge.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - Renewal reminder email 7 days before billing date.
  - Email states: plan, amount, billing date, link to cancel.

---

### US-BILL-10
**As a** user with a failed payment,  
**I want** to receive a clear notification and instructions to update my payment method,  
**So that** my account is not unexpectedly suspended.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Immediate email on payment failure: reason, link to update card.
  - In-app banner on next login.
  - 3 retry attempts over 7 days (Stripe dunning) before account downgrade.
  - Account downgraded (not deleted) on final failure.

---

### US-BILL-11
**As a** user,  
**I want** to switch from monthly to annual billing to save money,  
**So that** I can reduce my costs.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - Annual plan option on pricing page and billing settings.
  - Annual pricing shown as monthly equivalent with savings badge ("Save 20%").
  - Switch applies at next billing cycle.

---

### US-BILL-12
**As a** Business plan user,  
**I want** to add team members to my plan,  
**So that** my colleagues can access shared analyses.

- **Priority:** Must Have (Business plan)
- **Persona:** Marcus, James
- **Acceptance Criteria:**
  - "Manage members" in workspace settings.
  - Add by email; invitation sent.
  - Up to 10 members on Business plan.
  - Per-member seat pricing applied where applicable.

---

### US-BILL-13
**As an** Enterprise customer,  
**I want** to receive a custom quote for my team,  
**So that** I can negotiate pricing appropriate for my organisation.

- **Priority:** Must Have (Enterprise)
- **Persona:** Marcus (CEO of large org)
- **Acceptance Criteria:**
  - "Contact sales" CTA on pricing page.
  - Contact form: name, email, company, team size, use case.
  - Response within 1 business day.

---

### US-BILL-14
**As a** user,  
**I want** to apply a promotional discount code,  
**So that** I can take advantage of a special offer.

- **Priority:** Should Have
- **Persona:** All
- **Acceptance Criteria:**
  - Promo code field in Stripe Checkout.
  - Invalid code: clear error message.
  - Valid code: discount shown before payment confirmation.

---

### US-BILL-15
**As a** user,  
**I want** to see my current plan, usage, and renewal date on a single billing overview page,  
**So that** I always know where I stand.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - Billing overview shows: plan name, monthly cost, next billing date, features included, usage vs limits.
  - Upgrade/downgrade CTA visible.

---

## 12. Settings

### US-SET-01
**As a** user,  
**I want** to update my name and email address,  
**So that** my profile information is current.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - Profile settings page: display name, email.
  - Email change triggers verification of new email.
  - Old email notified of change.

---

### US-SET-02
**As a** user,  
**I want** to change my password,  
**So that** I can maintain my account security.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - Requires current password confirmation.
  - New password meets strength requirements.
  - Success email confirmation sent.

---

### US-SET-03
**As a** user,  
**I want** to manage email notification preferences,  
**So that** I only receive emails I find valuable.

- **Priority:** Should Have
- **Acceptance Criteria:**
  - Toggle options: analysis complete, share viewed, billing, product updates, weekly digest.
  - Changes saved immediately.

---

### US-SET-04
**As a** user,  
**I want** to view how much of my storage and upload quota I have used,  
**So that** I can plan my usage.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - Usage bar: analyses used / limit, storage used / limit.
  - Reset date shown.

---

### US-SET-05
**As a** user,  
**I want** to set my default currency for analysis,  
**So that** the system uses the correct currency for all new analyses.

- **Priority:** Should Have
- **Acceptance Criteria:**
  - Currency selector (ISO 4217).
  - Applied to all new analyses; does not retroactively affect existing.

---

### US-SET-06
**As a** user,  
**I want** to set my default date format,  
**So that** dates in my datasets are interpreted correctly.

- **Priority:** Should Have
- **Acceptance Criteria:**
  - Date format options: DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD.
  - Applied as hint when parsing date columns.

---

### US-SET-07
**As a** user,  
**I want** to export all my data from the platform,  
**So that** I can exercise my GDPR data portability rights.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - "Export my data" in settings.
  - Export includes: all analyses (CSV, PDF), account metadata (JSON).
  - Email with download link within 24 hours.
  - Download link valid for 7 days.

---

### US-SET-08
**As a** user,  
**I want** to connect and disconnect my Google account,  
**So that** I can manage which social logins are linked to my account.

- **Priority:** Should Have
- **Acceptance Criteria:**
  - Connected accounts list in settings.
  - Connect button opens OAuth flow.
  - Disconnect requires password confirmation if it is the only authentication method.

---

### US-SET-09
**As a** user,  
**I want** to switch between light and dark mode,  
**So that** I can use the app comfortably in different lighting conditions.

- **Priority:** Could Have
- **Acceptance Criteria:**
  - Theme toggle in settings and accessible from navigation.
  - Preference stored in user account (not just browser).
  - Default follows system preference.

---

### US-SET-10
**As a** user,  
**I want** to view the version number and last update date of the app,  
**So that** I know I am using the latest version.

- **Priority:** Could Have
- **Acceptance Criteria:**
  - App version visible in settings footer.
  - "What's new" link to changelog.

---

## 13. Administration

### US-ADM-01
**As an** admin,  
**I want** to view all members in my workspace,  
**So that** I can manage access and permissions.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - Members list: name, email, role, last active, joined date.
  - Sorted by last active.

---

### US-ADM-02
**As an** admin,  
**I want** to invite new members to my workspace by email,  
**So that** my team can collaborate on analyses.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - Email invitation sent within 30 seconds.
  - Invitation link valid for 7 days.
  - Role assigned at invitation: Admin, Analyst, Viewer.

---

### US-ADM-03
**As an** admin,  
**I want** to change a member's role,  
**So that** I can adjust permissions as the team evolves.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - Role dropdown per member.
  - Change takes effect immediately.
  - Member notified of role change by email.

---

### US-ADM-04
**As an** admin,  
**I want** to remove a member from the workspace,  
**So that** former employees cannot access company analyses.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - Remove option per member.
  - Confirmation required.
  - Removed member loses access immediately.
  - Their analyses remain in the workspace; ownership transfers to admin.

---

### US-ADM-05
**As an** admin,  
**I want** to view all analyses in the workspace,  
**So that** I have oversight of data activity.

- **Priority:** Should Have
- **Acceptance Criteria:**
  - Workspace analyses list: name, owner, created date, status.
  - Admins can view any analysis in the workspace.

---

### US-ADM-06
**As an** admin,  
**I want** to transfer workspace ownership,  
**So that** the billing and admin responsibilities can be assigned to another person.

- **Priority:** Should Have
- **Acceptance Criteria:**
  - "Transfer ownership" in workspace settings.
  - Target user must accept the transfer.
  - Previous owner retains Admin role after transfer.

---

### US-ADM-07
**As an** admin,  
**I want** to view a workspace audit log,  
**So that** I can track who did what and when.

- **Priority:** Should Have (Business plan)
- **Acceptance Criteria:**
  - Audit log: timestamp, user, action, affected resource.
  - Filterable by user, action type, date range.
  - Exportable as CSV.

---

### US-ADM-08
**As an** admin,  
**I want** to set a workspace-wide data retention policy,  
**So that** analyses are automatically archived or deleted after a defined period.

- **Priority:** Could Have
- **Acceptance Criteria:**
  - Retention options: 30 days, 90 days, 1 year, 3 years, indefinite.
  - Users notified before their analyses are deleted.

---

### US-ADM-09
**As an** admin,  
**I want** to view the workspace's total storage and upload usage,  
**So that** I can manage costs and capacity.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - Usage dashboard: total uploads, total storage, breakdown by member.
  - Usage trend over time.

---

## 14. Team Collaboration

### US-COL-01
**As a** team member,  
**I want** to see all analyses shared within my workspace,  
**So that** I can access work my colleagues have done.

- **Priority:** Must Have (Business plan)
- **Persona:** Marcus, James, Amara
- **Acceptance Criteria:**
  - Shared workspace library accessible to all members.
  - Analyses visible by: name, owner, date, tags.

---

### US-COL-02
**As a** user,  
**I want** to share a specific analysis with a workspace member,  
**So that** I can get their input.

- **Priority:** Must Have
- **Persona:** All
- **Acceptance Criteria:**
  - "Share with team" option on analysis.
  - Select specific members or share to all workspace.
  - Shared analysis appears in recipient's workspace library.

---

### US-COL-03
**As a** viewer in a workspace,  
**I want** to view shared analyses without editing them,  
**So that** I can consume the analysis without accidentally changing it.

- **Priority:** Must Have
- **Acceptance Criteria:**
  - Viewer role sees full dashboard but no edit controls.
  - AI chat available to viewers.
  - Export available to viewers.

---

### US-COL-04
**As a** user,  
**I want** to leave a comment on an insight,  
**So that** I can discuss findings with my team.

- **Priority:** Should Have (V1.1)
- **Persona:** Marcus, Priya, James
- **Acceptance Criteria:**
  - Comment icon on each insight card.
  - Threaded comments.
  - @mention support; mentioned user notified.
  - Comments visible to all workspace members with access.

---

### US-COL-05
**As a** workspace member,  
**I want** to be notified when a team member shares an analysis with me,  
**So that** I know when new content is available.

- **Priority:** Should Have
- **Acceptance Criteria:**
  - In-app notification and optional email.
  - Notification links directly to the shared analysis.

---

### US-COL-06
**As a** user,  
**I want** to see which team members have viewed a shared analysis,  
**So that** I know who has seen the data.

- **Priority:** Could Have
- **Persona:** Marcus, Oliver
- **Acceptance Criteria:**
  - "Viewed by" list with timestamps.
  - Visible to analysis owner and admins only.

---

### US-COL-07
**As a** user,  
**I want** to duplicate an analysis,  
**So that** I can use it as a starting point for a new analysis without overwriting the original.

- **Priority:** Should Have
- **Acceptance Criteria:**
  - "Duplicate" option in analysis menu.
  - Duplicated analysis: same dashboard, same data, new name: "[Original Name] — Copy".
  - User can immediately rename.

---

### US-COL-08
**As a** user,  
**I want** to tag analyses with labels,  
**So that** I can organise them by project, client, or topic.

- **Priority:** Could Have
- **Persona:** Oliver, Amara
- **Acceptance Criteria:**
  - Free-text tags per analysis.
  - Filter analyses list by tag.
  - Workspace-wide tag autocomplete.

---

### US-COL-09
**As a** team member,  
**I want** to star analyses as favourites,  
**So that** I can quickly find the analyses I use most.

- **Priority:** Could Have
- **Persona:** All
- **Acceptance Criteria:**
  - Star icon per analysis in library.
  - "Starred" filter in analysis list.
  - Starred analyses shown at top of home screen.

---

### US-COL-10
**As a** workspace admin,  
**I want** to archive old analyses,  
**So that** the workspace library stays uncluttered.

- **Priority:** Could Have
- **Persona:** Amara, Marcus
- **Acceptance Criteria:**
  - Archive option per analysis.
  - Archived analyses hidden from default view.
  - "Archived" filter to access archived analyses.
  - Restore available.

---

### US-COL-11
**As a** user,  
**I want** to see a recent activity feed for my workspace,  
**So that** I can stay up to date with what my team has analysed.

- **Priority:** Could Have
- **Persona:** Marcus, Amara
- **Acceptance Criteria:**
  - Activity feed on workspace home: who uploaded, shared, or commented, and when.
  - Last 30 events shown.
  - Real-time updates (or refresh within 30 seconds).
