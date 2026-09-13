"""Plain English for model-written text.

The strings here are not invented: they are what gpt-4o actually returned for
the GMPP portfolio *after* the prompt was given an explicit list of words never
to use. Prompt instructions did not hold, so the wording is corrected in code.
"""

from __future__ import annotations

from app.analytics.plain_language import plain_english, plain_english_in_place

# Verbatim from a successful response on 2026-09-13.
REAL_SUMMARY = (
    "The analysis reveals significant financial variances and outliers in the dataset. "
    "One project, the Midland Main Line Programme, shows an unusually high financial "
    "year variance of 733%. These anomalies suggest areas for further investigation."
)


def test_the_models_own_jargon_is_replaced():
    plain = plain_english(REAL_SUMMARY)

    for word in ("outlier", "dataset", "anomal"):
        assert word not in plain.lower()
    assert "unusually high or low figures" in plain
    assert "in the file" in plain
    assert "unusual results" in plain


def test_the_readers_own_column_names_survive():
    """"Variance" is the name of a column in this portfolio, not statistics
    jargon. Replacing it would make the text wrong rather than plain."""
    plain = plain_english(REAL_SUMMARY)

    assert "financial year variance of 733%" in plain
    assert "Midland Main Line Programme" in plain


def test_capitalisation_is_kept_at_the_start_of_a_sentence():
    assert plain_english("Outliers dominate.").startswith("Unusually high or low figures")
    assert plain_english("The dataset is large.").startswith("The file")


def test_every_reader_facing_string_in_a_result_is_cleaned():
    result = {
        "executive_summary": "The dataset has outliers.",
        "recommendations": [
            {"title": "Review the anomaly", "description": "Check the correlation.",
             "column": "revenue_dataset_id"},
        ],
    }

    cleaned = plain_english_in_place(result)

    assert cleaned["executive_summary"] == "The file has unusually high or low figures."
    assert cleaned["recommendations"][0]["title"] == "Review the unusual result"
    assert cleaned["recommendations"][0]["description"] == "Check the relationship."
    # Machine-readable fields are left alone: a column name is an identifier.
    assert cleaned["recommendations"][0]["column"] == "revenue_dataset_id"
