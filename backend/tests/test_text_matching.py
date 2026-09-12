"""The shared text vocabularies.

These drive decisions across the pipeline — which columns are metrics, which
category values fold into one chart slice, and how a label reads in a title or
an insight sentence — so they are tested directly rather than only through
their callers.
"""

from __future__ import annotations

from app.analytics.text_matching import (
    contains_keyword,
    is_unreported_category,
    is_withheld_value,
    shorten_label,
)


def test_shorten_label_cuts_on_a_word_boundary_and_marks_the_cut():
    long_label = "Ipa Delivery Confidence Assessment Of The Project At A Fixed Point In Time"

    short = shorten_label(long_label, 40)

    assert short.endswith("…")
    assert len(short) <= 41  # the ellipsis is one character past the limit
    assert long_label.startswith(short.removesuffix("…"))


def test_a_label_that_already_fits_is_untouched():
    assert shorten_label("Department", 40) == "Department"


def test_a_single_word_longer_than_the_limit_is_still_cut():
    """No word boundary to cut on, so it cuts mid-word rather than returning
    the whole paragraph."""
    assert shorten_label("Supercalifragilistic" * 5, 10).endswith("…")
    assert len(shorten_label("Supercalifragilistic" * 5, 10)) == 11


def test_withheld_values_are_recognised():
    assert is_withheld_value("Exempt under Section 43 of the Freedom of Information Act 2000")
    assert is_withheld_value("Not available")
    assert is_withheld_value("Redacted")
    assert not is_withheld_value("Amber")
    assert not is_withheld_value("1,234")


def test_unreported_categories_cover_withheld_values_and_blank_labels():
    """A chart folds these into one slice; the RAG states must not fold."""
    assert is_unreported_category("Unknown")
    assert is_unreported_category("Not Applicable")
    assert is_unreported_category("n/a")
    assert is_unreported_category("-")
    assert is_unreported_category("Exempt under Section 24 of the Freedom of Information Act 2000")

    assert not is_unreported_category("Red")
    assert not is_unreported_category("Amber")
    assert not is_unreported_category("Green")


def test_contains_keyword_matches_whole_tokens_only():
    # "arr" inside "n-arr-ative" typed narrative text as annual recurring revenue.
    assert not contains_keyword("departmental_narrative_on_schedule", ["arr"])
    # "arr" matches only as its own token — the column above is matched by the
    # ARR vocabulary's full phrase instead, which is why the narrative is safe.
    assert contains_keyword("arr", ["arr"])
    assert contains_keyword("annual_recurring_revenue", ["annual recurring revenue"])
    # Plurals still match their singular keyword.
    assert contains_keyword("whole_life_costs", ["cost"])
