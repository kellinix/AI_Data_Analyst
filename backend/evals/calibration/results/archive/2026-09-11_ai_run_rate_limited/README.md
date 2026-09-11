# Archived: the 2026-09-11 AI run (not used for calibration)

`summary.json` and `REPORT.md` here are from the one full run with gpt-4o analysis and the
LLM judge. They are kept as evidence for why that run was not used, not as results.

**Why it was discarded:**

1. **Rate limits.** The OpenAI key hit 527 HTTP 429 responses against 390 successes. In 19 of
   48 datasets both analysis calls failed and the pipeline fell back to its deterministic
   summary, leaving no AI recommendations to score. The failures skewed toward weekly
   datasets (larger prompts), so the AI tiers were measured on an unrepresentative subset.
2. **The judge misgraded data-quality claims.** It agreed with the deterministic labels on
   39/39 anomaly and 70/70 forecast recommendations, but only 13/26 on data-quality ones.
   Two causes, both since fixed: the product's data-quality recommendation did not name the
   column it flagged ("78.2% of values are missing"), and the judge prompt let "a known
   defect" be read as "not a problem". Every judge verdict on a data-quality claim in this
   run — AI or rule — is therefore suspect.

Its AI-tier numbers (`ai:high` hit rate 0.49 at confidence 0.85; `ai:medium` 0.54 at 0.70)
point to overconfidence, but given (1) and (2) they are an unvalidated indication only.
They were not written to the calibration table; the AI tiers keep their hand-set defaults.
See `docs/analytics/10_Confidence_Calibration.md`.
