# Data Quality Report — Northwind Outfitters — Weekly Sales

Generated: `2026-08-02T13:49:15+00:00`  
Rows: **936** · Columns: **10** · Checks run: **17** · Checks failed: **3**

## Overall score: 99/100

**Excellent** — ready for automated / unattended use.

## Findings

| Check | Column | Severity | Result |
|---|---|---|---|
| outliers | revenue | ❌ MEDIUM | 13 outlier value(s) in revenue (iqr) |
| outliers | marketing_spend | ❌ MEDIUM | 18 outlier value(s) in marketing_spend (iqr) |
| outliers | units_sold | ❌ MEDIUM | 14 outlier value(s) in units_sold (iqr) |
| missing_values | week_start_date | ✅ Pass | No missing values |
| missing_values | region | ✅ Pass | No missing values |
| missing_values | category | ✅ Pass | No missing values |
| missing_values | channel | ✅ Pass | No missing values |
| missing_values | revenue | ✅ Pass | No missing values |
| missing_values | units_sold | ✅ Pass | No missing values |
| missing_values | avg_order_value | ✅ Pass | No missing values |
| missing_values | new_customers | ✅ Pass | No missing values |
| missing_values | marketing_spend | ✅ Pass | No missing values |
| missing_values | discount_pct | ✅ Pass | No missing values |
| duplicate_records | week_start_date, region, category | ✅ Pass | No duplicate keys (week_start_date, region, category) |
| unexpected_nulls | region | ✅ Pass | region: no unexpected nulls |
| unexpected_nulls | category | ✅ Pass | category: no unexpected nulls |
| date_validity | week_start_date | ✅ Pass | week_start_date: all dates valid |

## Details on failed checks

### outliers — `revenue`
- Severity: **medium**
- Affected: **13** of 936 (1.4%)
- 13 outlier value(s) in revenue (iqr)
- Details: lower=5,415.30, upper=20,504.43, q1=11,073.72, q3=14,846.00

### outliers — `marketing_spend`
- Severity: **medium**
- Affected: **18** of 936 (1.9%)
- 18 outlier value(s) in marketing_spend (iqr)
- Details: lower=471.02, upper=2,620.53, q1=1,277.09, q3=1,814.47

### outliers — `units_sold`
- Severity: **medium**
- Affected: **14** of 936 (1.5%)
- 14 outlier value(s) in units_sold (iqr)
- Details: lower=83.50, upper=439.50, q1=217.00, q3=306.00
