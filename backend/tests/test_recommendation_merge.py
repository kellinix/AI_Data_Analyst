from __future__ import annotations

from app.services.analysis_engine import _merge_recommendations


def test_ai_and_deterministic_cards_citing_same_evidence_are_merged():
    """An AI recommendation and a deterministic one built from the same
    anomaly are one finding worded twice — only the first should survive."""
    ai = [{
        "title": "Significant outlier in 'chol' column.",
        "evidence": "One record reached 564.00 for Chol, higher than almost every other record.",
    }]
    deterministic = [{
        "title": "Review the context behind standout Chol",
        "evidence": "One record reached 564.00 for Chol, higher than almost every other record.",
    }]

    merged = _merge_recommendations(ai, deterministic)

    assert len(merged) == 1
    assert merged[0]["title"] == "Significant outlier in 'chol' column."


def test_distinct_evidence_is_kept():
    ai = [{"title": "Fix duplicates", "evidence": "723 duplicate rows."}]
    deterministic = [{"title": "Review standout Chol", "evidence": "One record reached 564.00."}]

    assert len(_merge_recommendations(ai, deterministic)) == 2


def test_same_field_coverage_finding_is_not_repeated_with_different_wording():
    ai = [{"title": "Missing values in Sr #_2", "evidence": "52.8% of Sr #_2 is missing"}]
    deterministic = [{"title": "Review coverage", "evidence": "Sr #_2 has 231 missing entries", "data": {"column": "Sr #_2"}}]
    assert len(_merge_recommendations(ai, deterministic)) == 1
