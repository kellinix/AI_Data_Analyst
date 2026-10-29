# Cross-industry report clarity review — 29 October 2026

## What was tested

Thirteen files went through the local file cleaner, production analysis engine,
plain-language presentation, PDF builder, and Excel builder. The analysis used
the offline AI fallback so the same inputs produce repeatable results. No cloud
deployment or paid AI call was made during this review. Source files stay local;
the four synthetic fixtures can be regenerated with
`python -m evals.reliability.generate_diverse_fixtures /tmp/zephyr_diverse_fixtures`.

| File / category | Analysed records | Excel charts | Main clarity check |
| --- | ---: | ---: | --- |
| Coffee sales | 3,636 | 4 | Sales amount and payment-method counts name sales records. |
| Supermarket sales | 1,400 | 5 | Sales totals lead; tax and prices do not masquerade as revenue. |
| University admissions | 400 | 4 | Admission chance is identified as a recorded estimate, not an acceptance rate. |
| Football players | 1,922 | 3 | Goals and assists are totals across player records; high performance is not called an error. |
| Chocolate shipments workbook | 7,905 | 5 | Calendar/reference sheets do not inflate shipment counts; shipment amount is named. |
| Government projects workbook | 19 | 4 | Baseline values retain their million-unit scale and weighted budget-change meaning. |
| Sponsorship-use workbook | 3,618 | 1 | Certificates used are summed; a source-sheet split is identified. |
| Student sponsor register | 1,374 | 4 | Counts describe register records, not people sponsored. |
| Worker sponsor register | 140,856 | 2 | Counts describe register records, not people sponsored. |
| Synthetic clinic appointments | 180 | 6 | Cancelled appointments are not treated as missing wait times. |
| Synthetic factory batches | 180 | 4 | Produced units are summed, while downtime is averaged. |
| Synthetic energy readings | 180 | 3 | Electricity use is summed and labelled in kWh. |
| Synthetic hiring applications | 180 | 6 | Hired share is labelled as an outcome, not a count. |

All thirteen imported and analysed without an unexplained row removal. Every
case produced a readable PDF and an Excel workbook with editable charts. The
CSV source row counts matched imported and analysed counts. For the three real
Excel workbooks, the parser's imported count matched the analysed count; the
separate source worksheets were reviewed for whether they should be joined.
The PDF from the shipment workbook was also rendered and visually inspected:
the summary, scope notes, monthly line, and labelled bars were present.

## Problems found and fixed locally

- A workbook's reference sheets could multiply or mix shipment records. They
  are now kept separate when a safe one-to-one join cannot be established.
- A long daily time series previously stopped after 100 plotted dates. It now
  groups by month while retaining the full measured total. The chart warns
  when the final month has unusually few recorded dates.
- An old shipment extract produced a forward-looking recommendation from a
  partial final month. Forecasts now reject stale extracts and exclude clearly
  incomplete final months from their calculation.
- Generic “entries,” unexplained abbreviations, and repeated source-system ID
  warnings obscured what each report counted. Reports now name their records,
  expand football shot terminology, and suppress a repeated salesperson-ID
  warning that did not indicate a problem.
- The PDF rounded a 12.5-million value to “12 million.” The million unit now
  keeps its decimal precision; PDF and Excel explain the scope of their figures.
- A high football penalty count was treated as a data problem. That generic
  anomaly recommendation is now suppressed for player statistics.

## Local validation

- Backend: `pytest -q` — **592 passed**.
- Changed backend files: `ruff check` — **passed**.
- Web and mobile TypeScript type checks — **passed**.
- Thirteen local pipeline cases — **13 completed, 0 processing errors, 0 generic-language flags**.

This is evidence for these files and the deterministic report path. It does
not prove that every future file will be understood correctly. Before charging
users, run a signed-in end-to-end trial with representative customer files,
review the live AI wording with nontechnical people, and check that they can
explain the figures and act on them without help. No deployment was triggered
by this review.
